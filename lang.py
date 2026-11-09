
import lngerr
from antlr4 import *
from antlr4.error.ErrorListener import *
from ExprLexer import ExprLexer
from ExprParser import ExprParser
from ExprVisitor import ExprVisitor
from dataclasses import dataclass
from typing import Callable, Any

add = lambda a, b: a + b
sub = lambda a, b: a - b
mul = lambda a, b: a * b
truediv = lambda a, b: a / b
less = lambda a, b: a < b
greater = lambda a, b: a > b
eq = lambda a, b: a == b
lesseq = lambda a, b: a <= b
greatereq = lambda a, b: a >= b

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
		int: {int: mul, float: mul},
		float: {int: mul, float: mul},
		str: {int: mul}
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
	}
}


@dataclass
class Slot:
	get: Callable
	set: Callable


class BreakSignal(Exception):
	def __init__(self, value):
		self.value = value

class ContinueSignal(Exception):
	...

class ReturnSignal(Exception):
	def __init__(self, value):
		self.value = value


@dataclass
class Function:
	args: list[str]
	body: Any
	sub_frames: list[dict]
	name: str = "<anonymous>"


class ExprExecuter(ExprVisitor):
	def __init__(self, src: str):
		self.frames: list[dict] = [{}, {"print": print}]
		self.src = src

	def error(self, msg, ctx):
		line = ctx.start.line
		col = ctx.start.column + 1
		lngerr.generic_error(msg, [(line, col)], self.src)

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

			if isinstance(atom, ExprParser.ArrayContext):
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
			return Slot(
				get = lambda: base.get()[index],
				set = lambda v: base.get().__setitem__(index, v)
			)

		self.error(f"invalid target {ctx!r}", ctx)


	def visitProgram(self, ctx):
		try:
			return self.execute_batch(ctx.expr())
		except BreakSignal, ContinueSignal, ReturnSignal:
			self.error("caonnot break, continue, or return on top level", ctx)


	def visitParen(self, ctx):
		return self.visit(ctx.expr())

	def visitUnary(self, ctx):
		v = self.visit(ctx.expr())
		return -v if ctx.getChild(0).getText() == "-" else +v


	def visitBinary(self, ctx):
		lhs = self.visit(ctx.expr(0))
		rhs = self.visit(ctx.expr(1))
		op = ctx.op.text

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


	def visitNamedFn(self, ctx):
		ids = ctx.ID()
		name = ids[0].getText()
		args = [a.getText() for a in ids[1:]]
		body = ctx.expr()

		sub_frames = self.frames.copy() # shallow copy: captures the frames when created
		fn = Function(args, body, sub_frames, name)

		self.create_frame_variable(name, fn, ctx)
		return fn

	def visitAnonyFn(self, ctx):
		args = [a.getText() for a in ctx.ID()]
		body = ctx.expr()

		sub_frames = self.frames.copy() # shallow copy: captures the frames when created
		fn = Function(args, body, sub_frames)

		return fn

	def visitCall(self, ctx):
		fn = self.visit(ctx.expr(0))
		args = [self.visit(t) for t in ctx.expr()[1:]]

		if callable(fn):
			return fn(*args)

		if isinstance(fn, Function):
			if len(args) != len(fn.args):
				self.error(f"{fn} requires {len(fn.args)} argument(s), got {len(args)} instead", ctx)

			# aliasing istead of copying here, because
			# step                                 self.frames   saved
			# -----------------------------------------------------------------
			# save old frames                      L1            L1
			# create a new list and rebind frames  L2            L1
			# run body                             L2 (mutated)  L1 (untouched)
			# restore frames                       L1            L1
			saved = self.frames
			
			self.frames = [dict(zip(fn.args, args))] + fn.sub_frames.copy() # rebind
			try:
				return self.visit(fn.body)
			except ReturnSignal as e:
				return e.value
			finally:
				self.frames = saved

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
		return ctx.STRNG().getText()[1:-1]

	def visitId(self, ctx):
		return self.as_slot(ctx).get()

	def visitArray(self, ctx):
		arr = []
		for i in ctx.expr():
			arr.append(self.visit(i))
		return arr

	def visitBlock(self, ctx):
		self.push_frame()
		val = self.execute_batch(ctx.expr())
		self.pop_frame()
		return val


class LangErrorListener(ErrorListener):
	def __init__(self, src: str):
		self.src = src

	def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
		lngerr.generic_error(f"{msg}", [(line, column + 1)], self.src)


def parse_and_execute(file_path):
	input_stream = FileStream(file_path, encoding="utf-8")

	with open(file_path, encoding="utf-8") as file:
		src = file.read()

	lexer = ExprLexer(input_stream)
	lexer.removeErrorListeners()
	lexer.addErrorListener(LangErrorListener(src))

	parser = ExprParser(CommonTokenStream(lexer))
	parser.removeErrorListeners()
	parser.addErrorListener(LangErrorListener(src))

	tree = parser.program()
	# print(tree.toStringTree(recog=parser))
	ExprExecuter(src).visit(tree)
