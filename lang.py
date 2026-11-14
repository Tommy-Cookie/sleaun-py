
import lngerr
import os
from antlr4 import *
from antlr4.error.ErrorListener import *
from ExprLexer import ExprLexer
from ExprParser import ExprParser
from ExprVisitor import ExprVisitor
from dataclasses import dataclass
from typing import Callable, Any


SLEAUN = ".slea"


add = lambda a, b: a + b
sub = lambda a, b: a - b
mul = lambda a, b: a * b
truediv = lambda a, b: a / b
less = lambda a, b: 1 if a < b else 0
greater = lambda a, b: 1 if a > b else 0
eq = lambda a, b: 1 if a == b else 0
lesseq = lambda a, b: 1 if a <= b else 0
greatereq = lambda a, b: 1 if a >= b else 0
bitand = lambda a, b: a & b
bitor = lambda a, b: a | b
bitxor = lambda a, b: a ^ b
andand = lambda a, b: a and b
oror = lambda a, b: a or b
lsh = lambda a, b: a << b
rsh = lambda a, b: a >> b

BINOP_TABLE = {
	"+": {
		int: {int: add, float: add},
		float: {int: add, float: add},
		str: {str: add}
	},
	"-": {
		int: {int: sub, float: sub},
		float: {int: sub, float: sub}
	},
	"*": {
		int: {int: mul, float: mul, str: mul, list: mul},
		float: {int: mul, float: mul},
		str: {int: mul},
		list: {int: mul}
	},
	"/": {
		int: {int: truediv, float: truediv},
		float: {int: truediv, float: truediv}
	},
	"<": {
		int: {int: less, float: less},
		float: {int: less, float: less}
	},
	">": {
		int: {int: greater, float: greater},
		float: {int: greater, float: greater}
	},
	"==": {
		int: {int: eq, float: eq},
		float: {int: eq, float: eq}
	},
	"<=": {
		int: {int: lesseq, float: lesseq},
		float: {int: lesseq, float: lesseq}
	},
	">=": {
		int: {int: greatereq, float: greatereq},
		float: {int: greatereq, float: greatereq}
	},
	"&": {
		int: {int: bitand}
	},
	"|": {
		int: {int: bitor}
	},
	"^": {
		int: {int: bitxor}
	},
	"&&": {
		int: {int: andand, float: andand, str: andand, list: andand},
		float: {int: andand, float: andand, str: andand, list: andand},
		str: {int: andand, float: andand, str: andand, list: andand},
		list: {int: andand, float: andand, str: andand, list: andand}
	},
	"||": {
		int: {int: oror, float: oror, str: oror, list: oror},
		float: {int: oror, float: oror, str: oror, list: oror},
		str: {int: oror, float: oror, str: oror, list: oror},
		list: {int: oror, float: oror, str: oror, list: oror}
	},
	"<<": {
		int: {int: lsh}
	},
	">>": {
		int: {int: rsh}
	}
}


class Unreachable(Exception):
	...


@dataclass
class Slot:
	get: Callable
	set: Callable


@dataclass
class CallInfo:
	line: int
	col: int
	file: str


class BreakSignal(Exception):
	def __init__(self, value):
		self.value = value

class ContinueSignal(Exception):
	...

class ReturnSignal(Exception):
	def __init__(self, value):
		self.value = value

class MismatchArgumentCount(Exception):
	def __init__(self, num_args):
		self.num_args = num_args


@dataclass
class Function:
	args: list[str]
	body: Any
	sub_frames: list[dict]
	file: str
	name: str = "<anonymous>"


def UNREACHABLE():
	raise Unreachable()


class ExprExecuter(ExprVisitor):
	def __init__(self, callstack, loading, cached, file, srcs: dict):
		self.frames: list[dict] = [{}, {"print": print, "true": 1, "false": 0, "null": None}]
		self.call_stack: list[CallInfo] = callstack
		self.loading: list[str] = loading
		self.cached: dict[str] = cached
		self.file = file
		self.srcs = srcs

	def error(self, msg, ctx):
		poses = [(ctx.start.line, ctx.start.column + 1, self.file)]

		for c in self.call_stack[::-1]:
			poses.append((c.line, c.col, c.file))

		lngerr.generic_error(msg, poses, self.srcs)

	def set_frame_variable(self, name, value, ctx):
		for f in self.frames:
			if name in f:
				f[name] = value
				return
		self.error(f"variable {name!r} doesn't exist", ctx)

	def create_frame_variable(self, name, value, ctx):
		if name in self.frames[0]:
			self.error(f"redefine variable {name!r}", ctx)
		self.frames[0][name] = value

	def get_frame_variable(self, name, ctx):
		for f in self.frames:
			if name in f:
				return f[name]
		self.error(f"variable {name!r} doesn't exist", ctx)

	def push_frame(self, frame=None):
		if frame is None:
			self.frames.insert(0, {})
		else:
			self.frames.insert(0, frame)

	def pop_frame(self):
		return self.frames.pop(0)

	def execute_batch(self, exprs):
		val = None
		for e in exprs:
			val = self.visit(e)
		return val

	def as_slot(self, ctx):
		if isinstance(ctx, ExprParser.SingleContext):
			atom = ctx.atom()

			if isinstance(atom, ExprParser.IdContext):
				name = atom.ID().getText()
				return Slot(
					get = lambda: self.get_frame_variable(name, atom),
					set = lambda v: self.set_frame_variable(name, v, atom)
				)

			if isinstance(atom, ExprParser.ArrayContext) or isinstance(atom, ExprParser.MapContext):
				value = self.visit(atom)
				return Slot(
					get = lambda: value,
					set = lambda _: self.error(f"invalid target {atom!r}", atom)
				)

		if isinstance(ctx, ExprParser.IdContext):
			name = ctx.ID().getText()
			return Slot(
				get = lambda: self.get_frame_variable(name, ctx),
				set = lambda v: self.set_frame_variable(name, v, ctx)
			)

		if isinstance(ctx, ExprParser.IndexContext):
			base = self.as_slot(ctx.expr(0))
			index = self.visit(ctx.expr(1))

			def _get():
				con = base.get()
				try:
					return con[index]
				except IndexError:
					self.error(f"index {index} out of range {len(con)}", ctx)
				except KeyError:
					self.error(f"key '{index}' doesn't exist", ctx)
				except TypeError:
					self.error(f"cannot index {type(con)}", ctx)

			def _set(v):
				con = base.get()
				try:
					con[index] = v
					return v
				except IndexError:
					self.error(f"index {index} out of range {len(con)}", ctx)
				except TypeError:
					self.error(f"cannot assign index {type(con)}", ctx)

			return Slot(get=_get, set=_set)

		if isinstance(ctx, ExprParser.AttrContext):
			base = self.as_slot(ctx.expr())
			attr = ctx.ID().getText()

			def _get():
				obj = base.get()
				try:
					return obj[attr]
				except KeyError:
					self.error(f"key '{attr}' doesn't exist", ctx)
				except TypeError:
					self.error(f"cannot index {type(obj)}", ctx)

			def _set(v):
				obj = base.get()
				try:
					obj[attr] = v
					return v
				except TypeError:
					self.error(f"cannot assign index {type(obj)}", ctx)

			return Slot(get=_get, set=_set)

		self.error(f"invalid target {ctx!r}", ctx)

	def perform_binop(self, lhs, rhs, op, ctx):
		if op == "/" and rhs == 0:
			if lhs == 0: return float("nan")
			if lhs < 0: return float("-inf")
			return float("inf")
		
		try:
			table = BINOP_TABLE[op]
		except KeyError:
			self.error(f"unknow infix operator {op!r}", ctx)
				
		try:
			fn = table[type(lhs)][type(rhs)]
		except KeyError:
			self.error(f"cannot apply {op!r} to {type(lhs)} and {type(rhs)}", ctx)
		
		return fn(lhs, rhs)

	def try_match(self, value, pctx):
		if isinstance(pctx, ExprParser.IntContext):
			return {} if type(value) is int and value == self.visit(pctx) else None
		if isinstance(pctx, ExprParser.FloatContext):
			return {} if type(value) is float and value == self.visit(pctx) else None
		if isinstance(pctx, ExprParser.StringContext):
			return {} if type(value) is str and value == self.visit(pctx) else None
		if isinstance(pctx, ExprParser.IdContext):
			return {pctx.ID().getText(): value}

		self.error(f"unsuported matching arm type {pctx!r}", pctx)

	def solve_entry(self, ctx):
		if isinstance(ctx, ExprParser.IdContext):
			return ctx.ID().getText()
		return self.visit(ctx)

	def solve_use(self, path: list[str], ctx):
		name = path[-1]
		rep = ".".join(path)

		if rep in self.cached:
			module = self.cached[rep]
			return name, module

		if rep in self.loading:
			start = self.loading.index(rep)
			chain = self.loading[start:] + [rep]
			self.error(f"circular using: '{"' -> '".join(chain)}'", ctx)

		path = "/".join(path) + SLEAUN
		path = os.path.abspath(path)

		self.loading.append(rep)
		try:
			with open(path, encoding="utf-8") as file:
				src = file.read()

			self.srcs[rep] = src
			module = parse_and_execute_src(src, self.call_stack, self.loading, self.cached, rep, self.srcs)
		except Exception as e:
			self.error(f"error while loading module '{rep}': {e}", ctx)
		finally:
			self.loading.pop()

		self.cached[rep] = module
		return name, module


	def visitProgram(self, ctx):
		try:
			return self.execute_batch(ctx.expr())
		except BreakSignal, ContinueSignal, ReturnSignal:
			self.error("caonnot break, continue, or return on top level", ctx)

	def visitUse(self, ctx):
		path = []
		for id in ctx.ID():
			path.append(id.getText())

		name, module = self.solve_use(path, ctx)
		self.create_frame_variable(name, module, ctx)

	def visitUseWithBind(self, ctx):
		path = []
		ids = ctx.ID()
		for id in ids[:-1]:
			path.append(id.getText())

		_, module = self.solve_use(path, ctx)
		self.create_frame_variable(ids[-1].getText(), module, ctx)
		# print(self.frames)


	def visitParen(self, ctx):
		return self.visit(ctx.expr())

	def visitUnary(self, ctx):
		v = self.visit(ctx.expr())
		op = ctx.op.text
		if op == "+":
			return +v
		if op == "-":
			return -v
		if op == "~":
			if type(v) is not int:
				self.error(f"cannot apply {op!r} to {v}")
			return ~v
		if op == "!":
			return 1 if not v else 0

		UNREACHABLE()


	def visitBinary(self, ctx):
		lhs = self.visit(ctx.expr(0))
		rhs = self.visit(ctx.expr(1))
		op = ctx.op.text

		return self.perform_binop(lhs, rhs, op, ctx)

	def visitInPlace(self, ctx):
		lhs = self.as_slot(ctx.expr(0))
		rhs = self.visit(ctx.expr(1))
		op = ctx.op.text[:-1]

		value = self.perform_binop(lhs.get(), rhs, op, ctx)
		lhs.set(value)
		return value
	

	def visitCreate(self, ctx):
		name = ctx.ID().getText()
		value = self.visit(ctx.expr())
		self.create_frame_variable(name, value, ctx)
		return value

	def visitAssign(self, ctx):
		slot = self.as_slot(ctx.expr(0))
		value = self.visit(ctx.expr(1))
		slot.set(value)
		return value

	def visitIndex(self, ctx):
		return self.as_slot(ctx).get()

	def visitAttr(self, ctx):
		return self.as_slot(ctx).get()


	def visitTernary(self, ctx):
		if self.visit(ctx.expr(0)):
			return self.visit(ctx.expr(1))
		return self.visit(ctx.expr(2))

	def visitWhile(self, ctx):
		cond = ctx.expr(0)
		body = ctx.expr()[1:]
		val = None
		try:
			while self.visit(cond):
				try:
					val = self.execute_batch(body)
				except ContinueSignal:
					pass
		except BreakSignal as e:
			val = e.value
		return val

	def visitBreak(self, ctx):
		value = ctx.expr()
		if value is not None:
			value = self.visit(value)
		raise BreakSignal(value)

	def visitContinue(self, ctx):
		raise ContinueSignal()

	def visitMatch(self, ctx):
		value = self.visit(ctx.expr())
	
		for arm in ctx.arm():
			binds = self.try_match(value, arm.atom())
			if binds is not None:
				self.push_frame(binds)
				try:
					return self.visit(arm.expr())
				finally:
					self.pop_frame()

		self.error(f"no pattern matched value {value!r}", ctx)


	def visitNamedFn(self, ctx):
		ids = ctx.ID()
		name = ids[0].getText()
		args = [a.getText() for a in ids[1:]]
		body = ctx.expr()

		sub_frames = self.frames.copy() # shallow copy: captures the frames when created
		fn = Function(args, body, sub_frames, self.file, name)

		self.create_frame_variable(name, fn, ctx)
		return fn

	def visitAnonyFn(self, ctx):
		args = [a.getText() for a in ctx.ID()]
		body = ctx.expr()

		sub_frames = self.frames.copy() # shallow copy: captures the frames when created
		fn = Function(args, body, sub_frames, self.file)

		return fn

	def visitCall(self, ctx):
		fn = self.visit(ctx.expr(0))
		args = [self.visit(t) for t in ctx.expr()[1:]]

		if callable(fn):
			try:
				return fn(*args)
			except MismatchArgumentCount as e:
				self.error(f"<builtin> requires {len(e.num_args)} argument(s), got {len(args)} instead", ctx)

		if isinstance(fn, Function):
			if len(args) != len(fn.args):
				self.error(f"{fn.name} requires {len(fn.args)} argument(s), got {len(args)} instead", ctx)

			self.call_stack.append(CallInfo(
				ctx.start.line, ctx.start.column + 1, self.file
			))
			# aliasing istead of copying here, because
			# step                                 self.frames   saved
			# -----------------------------------------------------------------
			# save old frames                      L1            L1
			# create a new list and rebind frames  L2            L1
			# run body                             L2 (mutated)  L1 (untouched)
			# restore frames                       L1            L1
			saved = self.frames
			saved_file = self.file
			
			self.frames = [dict(zip(fn.args, args))] + fn.sub_frames.copy() # rebind
			self.file = fn.file
			try:
				return self.visit(fn.body)
			except ReturnSignal as e:
				return e.value
			finally:
				self.frames = saved
				self.file = saved_file
				self.call_stack.pop()

		self.error(f"{type(fn)} is not callable", ctx)

	def visitReturn(self, ctx):
		value = ctx.expr()
		if value is not None:
			value = self.visit(value)
		raise ReturnSignal(value)


	def visitSingle(self, ctx):
		return self.visit(ctx.atom())

	def visitFloat(self, ctx):
		return float(ctx.FLOAT().getText())

	def visitInt(self, ctx):
		return int(ctx.INT().getText())

	def visitString(self, ctx):
		return ctx.STRING().getText()[1:-1]

	def visitId(self, ctx):
		return self.as_slot(ctx).get()

	def visitArray(self, ctx):
		arr = []
		for i in ctx.expr():
			arr.append(self.visit(i))
		return arr

	def visitMap(self, ctx):
		mp = {}
		for e in ctx.entry():
			key = self.solve_entry(e.atom())
			value = self.visit(e.expr())
			mp[key] = value
		return mp

	def visitBlock(self, ctx):
		self.push_frame()
		try:
			val = self.execute_batch(ctx.expr())
		finally:
			self.pop_frame()
		return val


class LangErrorListener(ErrorListener):
	def __init__(self, file: str, srcs):
		self.file = file
		self.srcs = srcs

	def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
		lngerr.generic_error(f"{msg}", [(line, column + 1, self.file)], self.srcs)


def module_name(file_path: str):
	norm = os.path.normpath(file_path)
	base = os.path.splitext(norm)[0]
	base = base.lstrip("./\\")
	return base.replace("/", ".").replace("\\", ".")


def parse_and_execute_src(src: str, callstack, loading, cached, file: str, srcs):
	input_stream = InputStream(src)

	lexer = ExprLexer(input_stream)
	lexer.removeErrorListeners()
	lexer.addErrorListener(LangErrorListener(file, srcs))
	
	parser = ExprParser(CommonTokenStream(lexer))
	parser.removeErrorListeners()
	parser.addErrorListener(LangErrorListener(file, srcs))
	
	tree = parser.program()
	return ExprExecuter(callstack, loading, cached, file, srcs).visit(tree)


def parse_and_execute(file_path):
	with open(file_path, encoding="utf-8") as file:
		src = file.read()

	rep = module_name(file_path)
	return parse_and_execute_src(src, [], [], {}, rep, {rep: src})
