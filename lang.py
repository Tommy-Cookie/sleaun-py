
import lngerr
import os, struct
from antlr4 import *
from antlr4.error.ErrorListener import *
from ExprLexer import ExprLexer
from ExprParser import ExprParser
from ExprVisitor import ExprVisitor
from dataclasses import dataclass
from typing import Callable, Any
from zlib import crc32


SLEAUN = ".slea"
"""
EXTENSION CONVENTION
[{namespace: {name: callable}}, ...]
list of extensions, extensions have its own namespace
"""


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
class WantsInterp:
	fn: Callable


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
	def __init__(self, callstack, loading, cached, file, srcs: dict, exts: list):
		self.frames: list[dict] = [{}, *exts, {
			"input": input, "print": print, "true": 1, "false": 0, "null": None
		}]
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
			module = parse_and_execute_src(src, self.call_stack, self.loading, self.cached, rep, self.srcs, self.exts)
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
		interp = False
		args = [self.visit(t) for t in ctx.expr()[1:]]

		if isinstance(fn, WantsInterp):
			fn = fn.fn
			interp = True

		if callable(fn):
			try:
				if interp: return fn(self, *args)
				else: return fn(*args)
			except MismatchArgumentCount as e:
				self.error(f"{fn.__name__} requires {len(e.num_args)} argument(s), got {len(args)} instead", ctx)
			except Exception as e:
				self.error(str(e))

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




Opcode = int
BYTE_BINARY = 0
BYTE_LOADI64 = 1
BYTE_LOAD = 2
BYTE_CALL = 3
BYTE_HALT = 4
BYTE_POP = 5
BYTE_CREATE = 6
BYTE_ASSIGN_VAR = 7
BYTE_ASSIGN_IDX = 8
BYTE_INDEX = 9
BYTE_LOADS = 10
BYTE_LOADF64 = 11
BYTE_MAKE_ARRAY = 12
BYTE_MAKE_MAP = 13
BYTE_JUMP = 14
BYTE_JUMP_FALSE = 15
BYTE_PUSH_FRAME = 16
BYTE_POP_FRAME = 17
BYTE_DUP = 18
BYTE_DUP_2 = 19
BYTE_LOADB = 20 # load blank
BYTE_TMP_PUSH = 21
BYTE_TMP_SET = 22
BYTE_TMP_LOAD = 23
BYTE_TMP_POP = 24
BYTE_UNARY = 25
BYTE_MAKE_FUNC = 26
BYTE_RETURN = 27
BYTE_MATCHI_FALSE = 28 # jump to param if match false, else binding
BYTE_MATCHF_FALSE = 29
BYTE_MATCHS_FALSE = 30
BYTE_MATCHB = 31 # match binding
BYTE_MATCH_MISS = 32
BYTE_USE = 33
BYTE_LOADI32 = 34
BYTE_LOADI16 = 35
BYTE_LOADI8 = 36


def print_bytecode(prog: Program):
	BYTE_TO_STRING = {
		BYTE_LOAD: "load",
		BYTE_LOADI64: "loadi64",
		BYTE_BINARY: "binary",
		BYTE_CALL: "call",
		BYTE_HALT: "halt",
		BYTE_POP: "pop",
		BYTE_CREATE: "create",
		BYTE_ASSIGN_VAR: "assign_var",
		BYTE_ASSIGN_IDX: "assign_idx",
		BYTE_INDEX: "index",
		BYTE_LOADS: "loads",
		BYTE_LOADF64: "loadf64",
		BYTE_MAKE_ARRAY: "make_array",
		BYTE_MAKE_MAP: "make_map",
		BYTE_JUMP: "jump",
		BYTE_JUMP_FALSE: "jump_false",
		BYTE_PUSH_FRAME: "push_frame",
		BYTE_POP_FRAME: "pop_frame",
		BYTE_DUP: "dup",
		BYTE_DUP_2: "dup_2",
		BYTE_LOADB: "loadb",
		BYTE_TMP_PUSH: "tmp_push",
		BYTE_TMP_SET: "tmp_set",
		BYTE_TMP_LOAD: "tmp_load",
		BYTE_TMP_POP: "tmp_pop",
		BYTE_UNARY: "unary",
		BYTE_MAKE_FUNC: "make_func",
		BYTE_RETURN: "return",
		BYTE_MATCHI_FALSE: "matchi_false",
		BYTE_MATCHF_FALSE: "matchf_false",
		BYTE_MATCHS_FALSE: "matchs_false",
		BYTE_MATCHB: "matchb", # match binding
		BYTE_MATCH_MISS: "match_miss",
		BYTE_USE: "use",
		BYTE_LOADI32: "loadi32",
		BYTE_LOADI16: "loadi16",
		BYTE_LOADI8: "loadi8"
	}
	print(f"[ program  file={prog.file} ]")
	for i, code in enumerate(prog.codes):
		print(f"==== code[{i}]  {code.name}  params={code.args} ====")
		n = 0
		for op, pa in code.code:
			print(f"{n:>5}  {BYTE_TO_STRING[op]:<13}  {repr(pa) if pa is not None else ""}")
			n += 1


@dataclass
class CodeObject:
	args: list[str]
	code: list[tuple]
	line_marks: list[tuple]
	name: str

@dataclass
class Program:
	codes: list[CodeObject]
	src: str
	file: str


SLEAUN_C_VERSION = 1
SLEAUN_MAGIC = b"SLEC"

I64 = 0
I32 = 1
I16 = 2
I8 = 3
F64 = 4
STRING = 5
U32 = 6
U8 = 7
U16 = 8
OPCODE_ARGS = {
	BYTE_BINARY: STRING,
	BYTE_LOADI64: I64,
	BYTE_LOAD: STRING,
	BYTE_CALL: U8,
	BYTE_CREATE: STRING,
	BYTE_ASSIGN_VAR: STRING,
	BYTE_LOADS: STRING,
	BYTE_LOADF64: F64,
	BYTE_MAKE_ARRAY: U32,
	BYTE_MAKE_MAP: U32,
	BYTE_JUMP: U32,
	BYTE_JUMP_FALSE: U32,
	BYTE_UNARY: STRING,
	BYTE_MAKE_FUNC: U16,
	BYTE_MATCHI_FALSE: U32,
	BYTE_MATCHF_FALSE: U32,
	BYTE_MATCHS_FALSE: U32,
	BYTE_MATCHB: STRING,
	BYTE_USE: STRING,
	BYTE_LOADI32: I32,
	BYTE_LOADI16: I16,
	BYTE_LOADI8: I8
}
"""
magic: SLEC
version: u16: 1
flags: u8 bit0: has_debug
string pool: [string pool]
codes: u32: length [code object]*
if flags.has_debug
	file: u32 length, chars data (no string pool)
	src: u32 length, chars data (no string pool)
u32: crc32 checksum

[bytecode]
u8: opcode, ...?: param

[code object]
name: [string]
args: u32: length, [string]*
code: u32: length, [bytecode]*
if flags.has_debug
	line marks: u32: count, ( u32: line, u32: col )*

[string pool]
u32: nmuber of strings
( u32: length, chars: data )*

[string]
u32: entry to string pool
"""
def dump_program(prog: Program):
	final = bytearray()
	string_pool = []
	data = bytearray()
	has_debug = 1

	def new_string(string: str) -> int:
		if string in string_pool:
			return string_pool.index(string)
		at = len(string_pool)
		string_pool.append(string)
		return at

	def pack_string(string: str):
		return struct.pack("<I", new_string(string))

	def pack_inline_str(dst: bytearray, string: str):
		encoded = bytes(string, encoding="utf-8")
		dst.extend(struct.pack("<I", len(encoded)))
		dst.extend(encoded)

	def pack_var(typ, val):
		if typ == I8: return struct.pack("<b", val)
		if typ == I16: return struct.pack("<h", val)
		if typ == I32: return struct.pack("<i", val)
		if typ == I64: return struct.pack("<q", val)
		if typ == F64: return struct.pack("<d", val)
		if typ == STRING: return pack_string(val)
		if typ == U8: return struct.pack("<B", val)
		if typ == U16: return struct.pack("<H", val)
		if typ == U32: return struct.pack("<I", val)
		return bytes()

	# header
	final.extend(SLEAUN_MAGIC)
	final.extend(struct.pack("<H", SLEAUN_C_VERSION))
	final.extend([has_debug]) # include debug

	# code object
	data.extend(struct.pack("<I", len(prog.codes)))
	for co in prog.codes:
		data.extend(pack_string(co.name))

		data.extend(struct.pack("<I", len(co.args)))
		for i in co.args:
			data.extend(pack_string(i))

		data.extend(struct.pack("<I", len(co.code)))
		for c in co.code:
			data.extend([c[0]])
			typ = OPCODE_ARGS.get(c[0], -1)
			data.extend(pack_var(typ, c[1]))

		if not has_debug:
			continue

		data.extend(struct.pack("<I", len(co.line_marks)))
		for l in co.line_marks:
			data.extend(struct.pack("<I", l[0]))
			data.extend(struct.pack("<I", l[1]))

	final.extend(struct.pack("<I", len(string_pool)))
	for i in string_pool:
		pack_inline_str(final, i)
	final.extend(data)

	if has_debug:
		pack_inline_str(final, prog.file)
		pack_inline_str(final, prog.src)

	crc = crc32(final)
	final.extend(struct.pack("<I", crc))

	return final


class LangVM:
	def __init__(self, prog: Program, cached=None, loading=None, exts=None, srcs=None):
		self.exts = exts if exts is not None else []
		self.frames: list[dict] = [{}, *self.exts, {
			"input": input, "print": print, "true": 1, "false": 0, "null": None
		}]
		self.call_stack: list[CallInfo] = []
		self.pc = 0
		self.code: CodeObject = prog.codes[0]
		self.line_marks = self.code.line_marks
		self.srcs = {prog.file: prog.src} if srcs is None else srcs
		self.stack = []
		self.temp = []
		self.prog = prog
		self.saved_states = []
		self.cached = cached if cached is not None else {}
		self.loading = loading if loading is not None else []
		self.file = prog.file

	def error(self, msg):
		p = self.line_marks[self.pc]
		poses = [(p[0], p[1], self.file)]
		for c in self.call_stack[::-1]:
			poses.append((c.line, c.col, c.file))
		lngerr.generic_error(msg, poses, self.srcs)

	def set_frame_variable(self, name, value):
		for f in self.frames:
			if name in f:
				f[name] = value
				return
		self.error(f"variable {name!r} doesn't exist")

	def create_frame_variable(self, name, value):
		if name in self.frames[0]:
			self.error(f"redefine variable {name!r}")
		self.frames[0][name] = value

	def get_frame_variable(self, name):
		for f in self.frames:
			if name in f:
				return f[name]
		self.error(f"variable {name!r} doesn't exist")

	def push_frame(self, frame=None):
		if frame is None:
			self.frames.insert(0, {})
		else:
			self.frames.insert(0, frame)

	def pop_frame(self):
		return self.frames.pop(0)

	def push(self, value):
		self.stack.append(value)

	def pop(self):
		return self.stack.pop()

	def top(self):
		return self.stack[-1]

	def perform_binop(self, lhs, rhs, op):
		if op == "/" and rhs == 0:
			if lhs == 0: return float("nan")
			if lhs < 0: return float("-inf")
			return float("inf")
		
		try:
			table = BINOP_TABLE[op]
		except KeyError:
			self.error(f"unknow infix operator {op!r}")
				
		try:
			fn = table[type(lhs)][type(rhs)]
		except KeyError:
			self.error(f"cannot apply {op!r} to {type(lhs)} and {type(rhs)}")
		
		return fn(lhs, rhs)



	def run(self):
		print_bytecode(self.prog)
		while True:
			op, param = self.code.code[self.pc]
			self.pc += 1

			if op == BYTE_LOAD:
				self.push(self.get_frame_variable(param))
			elif op == BYTE_LOADI64 or op == BYTE_LOADI32 or op == BYTE_LOADI16 or op == BYTE_LOADI8:
				self.push(param)
			elif op == BYTE_LOADF64:
				self.push(param)
			elif op == BYTE_LOADS:
				self.push(param)
			elif op == BYTE_LOADB:
				self.push(None)
			
			elif op == BYTE_BINARY:
				rhs = self.pop()
				lhs = self.pop()
				self.push(self.perform_binop(lhs, rhs, param))

			elif op == BYTE_CALL:
				args = []
				for i in range(param):
					args.insert(0, self.pop())
				fn = self.pop()

				if callable(fn):
					self.push(fn(*args))

				elif isinstance(fn, Function):
					if len(args) != len(fn.args):
						self.error(f"{fn.name} requires {len(fn.args)} argument(s), got {len(args)} instead")

					lmark = self.line_marks[self.pc - 1]
					self.call_stack.append(CallInfo(*lmark, self.file))

					self.saved_states.append((
						self.code, self.pc, self.frames, self.line_marks, self.file
					))
					self.code = fn.body
					self.pc = 0
					self.line_marks = fn.body.line_marks
					self.file = fn.file
					self.frames = [dict(zip(fn.args, args))] + fn.sub_frames.copy()

				else:
					self.error(f"{fn} is not callable")

			elif op == BYTE_RETURN:
				self.call_stack.pop()
				self.code, self.pc, self.frames, self.line_marks, self.file = self.saved_states.pop()

			elif op == BYTE_HALT:
				break
			elif op == BYTE_POP:
				self.pop()

			elif op == BYTE_CREATE:
				value = self.top()
				self.create_frame_variable(param, value)
			elif op == BYTE_ASSIGN_VAR:
				value = self.top()
				self.set_frame_variable(param, value)

			elif op == BYTE_INDEX:
				index = self.pop()
				target = self.pop()
				try:
					self.push(target[index])
				except IndexError:
					self.error(f"index {index} out of range {len(target)}")
				except KeyError:
					self.error(f"key '{index}' doesn't exist")
				except TypeError:
					self.error(f"cannot index {type(target)}")
			elif op == BYTE_ASSIGN_IDX:
				value = self.pop()
				index = self.pop()
				target = self.pop()
				try:
					target[index] = value
				except IndexError:
					self.error(f"index {index} out of range {len(target)}")
				except TypeError:
					self.error(f"cannot assign index {type(target)}")
				self.push(value)

			elif op == BYTE_MAKE_ARRAY:
				array = []
				for i in range(param):
					array.insert(0, self.pop())
				self.push(array)
			elif op == BYTE_MAKE_MAP:
				mp = {}
				for i in range(param):
					val = self.pop()
					key = self.pop()
					mp[key] = val
				self.push(mp)

			elif op == BYTE_JUMP:
				self.pc = param
			elif op == BYTE_JUMP_FALSE:
				cond = self.pop()
				if not cond:
					self.pc = param

			elif op == BYTE_PUSH_FRAME:
				self.push_frame()
			elif op == BYTE_POP_FRAME:
				self.pop_frame()

			elif op == BYTE_DUP:
				self.push(self.top())
			elif op == BYTE_DUP_2:
				self.push(self.stack[-2])
				self.push(self.stack[-2])

			elif op == BYTE_TMP_PUSH:
				self.temp.append(self.top())
			elif op == BYTE_TMP_POP:
				self.temp.pop()
			elif op == BYTE_TMP_SET:
				value = self.top()
				self.temp[-1] = value
			elif op == BYTE_TMP_LOAD:
				self.push(self.temp[-1])

			elif op == BYTE_UNARY:
				value = self.pop()
				if param == "+":
					self.push(+value)
				if param == "-":
					self.push(-value)
				if param == "~":
					if type(value) is not int:
						self.error(f"cannot apply {param!r} to {value}")
					self.push(~value)
				if param == "!":
					self.push(1 if not value else 0)

			elif op == BYTE_MAKE_FUNC:
				code: CodeObject = self.prog.codes[param]
				sub_frames = self.frames.copy()
				self.push(Function(
					code.args, code, sub_frames, self.file, code.name
				))

			elif op == BYTE_MATCHI_FALSE:
				value = self.pop()
				target = self.top()
				if not (type(target) is int and target == value):
					self.pc = param
				else:
					self.push_frame()
			elif op == BYTE_MATCHF_FALSE:
				value = self.pop()
				target = self.top()
				if not (type(target) is float and target == value):
					self.pc = param
				else:
					self.push_frame()
			elif op == BYTE_MATCHS_FALSE:
				value = self.pop()
				target = self.top()
				if not (type(target) is str and target == value):
					self.pc = param
				else:
					self.push_frame()
			elif op == BYTE_MATCHB:
				value = self.top()
				self.push_frame({param: value})
			elif op == BYTE_MATCH_MISS:
				self.error(f"no pattern matched value {self.pop()}")

			elif op == BYTE_USE:
				path: list[str] = param.split(".")
				rep: str = param

				if rep in self.cached:
					self.push(self.cached[rep])
					continue

				if rep in self.loading:
					start = self.loading.index(rep)
					chain = self.loading[start:] + [rep]
					self.error(f"circular using: '{"' -> '".join(chain)}'")

				path = "/".join(path) + SLEAUN
				path = os.path.abspath(path)
				self.loading.append(rep)
				try:
					with open(path, encoding="utf-8") as file:
						src = file.read()

					self.srcs[rep] = src
					tree = parse_src(src, rep)
					prog = compile_program(tree, src, rep)
					vm = LangVM(prog, self.cached, self.loading, self.exts, self.srcs)
					module = vm.run()
				except Exception as e:
					self.error(f"error while loading module '{rep}': {e}")
				finally:
					self.loading.pop()

				self.cached[rep] = module
				self.push(module)
			else:
				UNREACHABLE()

			# print(self.frames, self.stack, self.temp)
		return self.stack[-1]


class Compiler(ExprVisitor):
	def __init__(self, file, srcs, codes):
		self.code = []
		self.line_marks = []
		self.pending = []
		self.labels = {}
		self.slots = 0
		self.file = file
		self.loop_stack = []
		self.frame_depth = 1
		self.srcs = srcs
		self.codes: list = codes

	def error(self, msg, ctx):
		poses = [(ctx.start.line, ctx.start.column, self.file)]
		for c in self.call_stack[::-1]:
			poses.append((c.line, c.col, c.file))
		lngerr.generic_error(msg, poses, self.srcs)

	def emit(self, ctx, opcode: Opcode, param: Any = None):
		# print(f"{opcode[1]}\t{param}")
		self.code.append((opcode, param))
		self.line_marks.append((ctx.start.line, ctx.start.column + 1))

		if opcode == BYTE_PUSH_FRAME: self.frame_depth += 1
		elif opcode == BYTE_POP_FRAME: self.frame_depth -= 1

	def next_slot(self):
		self.slots += 1
		return self.slots

	def new_label(self):
		return self.next_slot()

	def emit_jump(self, ctx, op, label):
		self.emit(ctx, op, 0)
		self.pending.append((len(self.code) - 1, label))

	def place_label(self, label):
		self.labels[label] = len(self.code)

	def resolve_label(self):
		for idx, label in self.pending:
			op, _ = self.code[idx]
			self.code[idx] = (op, self.labels[label])
		self.pending.clear()

	def solve_entry(self, ctx):
		if isinstance(ctx, ExprParser.IdContext):
			self.emit(ctx, BYTE_LOADS, ctx.ID().getText())
		else:
			self.visit(ctx)

	def visit_batch(self, exprs, ctx):
		if len(exprs) == 0:
			self.emit(ctx, BYTE_LOADB)
			return
		for i, e in enumerate(exprs, 1):
			self.visit(e)
			if len(exprs) - i != 0:
				self.emit(e, BYTE_POP)

	def solve_function(self, body, params, name):
		idx = len(self.codes)
		self.codes.append(None)

		sub = Compiler(self.file, self.srcs, self.codes)
		sub.visit(body)
		sub.emit(body, BYTE_RETURN)
		sub.resolve_label()

		self.codes[idx] = CodeObject(
			params, sub.code, sub.line_marks, name
		)
		return idx

	def solve_use(self, ctx, ids):
		path = [i.getText() for i in ids]
		path = ".".join(path)
		self.emit(ctx, BYTE_USE, path)
		return path[-1]


	def visitUse(self, ctx):
		name = self.solve_use(ctx, ctx.ID())
		self.emit(ctx, BYTE_CREATE, name)
		self.emit(ctx, BYTE_POP)
		self.emit(ctx, BYTE_LOADB)

	def visitUseWithBind(self, ctx):
		ids = ctx.ID()
		self.solve_use(ctx, ids[:-1])
		self.emit(ctx, BYTE_CREATE, ids[-1].getText())
		self.emit(ctx, BYTE_POP)
		self.emit(ctx, BYTE_LOADB)


	def visitProgram(self, ctx):
		self.visit_batch(ctx.expr(), ctx)
		self.emit(ctx, BYTE_HALT)
		self.resolve_label()

	def visitBinary(self, ctx):
		op = ctx.op.text
		self.visit(ctx.expr(0))
		self.visit(ctx.expr(1))
		self.emit(ctx, BYTE_BINARY, op)

	def visitUnary(self, ctx):
		op = ctx.op.text
		self.visit(ctx.expr())
		self.emit(ctx, BYTE_UNARY, op)

	def visitInPlace(self, ctx):
		lhs = ctx.expr(0)
		rhs = ctx.expr(1)
		op = ctx.op.text[:-1]

		if isinstance(lhs, ExprParser.SingleContext):
			atom = lhs.atom()
			if isinstance(atom, ExprParser.IdContext):
				name = atom.ID().getText()
				self.emit(atom, BYTE_LOAD, name)
				self.visit(rhs)
				self.emit(atom, BYTE_BINARY, op)
				self.emit(atom, BYTE_ASSIGN_VAR, name)
				return

		if isinstance(lhs, ExprParser.IndexContext):
			self.visit(lhs.expr(0)) # a	
			self.visit(lhs.expr(1))	# a, i
			self.emit(lhs, BYTE_DUP_2) # a, i, a, i
			self.emit(lhs, BYTE_INDEX) # a, i, a[i]
			self.visit(rhs) # a, i, a[i], v
			self.emit(lhs, BYTE_BINARY, op) # a, i, a[i] op v
			self.emit(lhs, BYTE_ASSIGN_IDX)
			return

		if isinstance(lhs, ExprParser.AttrContext):
			self.visit(lhs.expr()) # a
			self.emit(lhs, BYTE_LOADS, lhs.ID().getText()) # a, i
			self.emit(lhs, BYTE_DUP_2) # a, i, a, i
			self.emit(lhs, BYTE_INDEX) # a, i, a[i]
			self.visit(rhs) # a, i, a[i], v
			self.emit(lhs, BYTE_BINARY, op) # a, i, a[i] op v
			self.emit(lhs, BYTE_ASSIGN_IDX)
			return

		UNREACHABLE()


	def visitNamedFn(self, ctx):
		ids = ctx.ID()
		name = ids[0].getText()
		params = [i.getText() for i in ids[1:]]
		idx = self.solve_function(ctx.expr(), params, name)
		self.emit(ctx, BYTE_MAKE_FUNC, idx)
		self.emit(ctx, BYTE_CREATE, name)

	def visitAnonyFn(self, ctx):
		params = [i.getText() for i in ctx.ID()]
		idx = self.solve_function(ctx.expr(), params, "<anonymous>")
		self.emit(ctx, BYTE_MAKE_FUNC, idx)


	def visitMatch(self, ctx):
		lend = self.new_label()
		labs = [self.new_label() for _ in ctx.arm()]

		self.visit(ctx.expr())

		for i, arm in enumerate(ctx.arm()):
			pat = arm.atom()
			body = arm.expr()
			nxtlab = labs[i]

			if isinstance(pat, ExprParser.IdContext):
				name = pat.ID().getText()
				self.emit(ctx, BYTE_MATCHB, name)
			elif isinstance(pat, ExprParser.IntContext):
				self.visit(pat)
				self.emit_jump(ctx, BYTE_MATCHI_FALSE, nxtlab)
			elif isinstance(pat, ExprParser.FloatContext):
				self.visit(pat)
				self.emit_jump(ctx, BYTE_MATCHF_FALSE, nxtlab)
			elif isinstance(pat, ExprParser.StringContext):
				self.visit(pat)
				self.emit_jump(ctx, BYTE_MATCHS_FALSE, nxtlab)
			else:
				self.error(f"unsuported matching arm type {pat!r}")

			self.emit(ctx, BYTE_POP)
			self.visit(body)
			self.emit_jump(ctx, BYTE_JUMP, lend)

			self.place_label(nxtlab)

		self.emit(ctx, BYTE_MATCH_MISS)
		self.place_label(lend)
		self.emit(ctx, BYTE_POP_FRAME)


	def visitCreate(self, ctx):
		self.visit(ctx.expr())
		self.emit(ctx, BYTE_CREATE, ctx.ID().getText())

	def visitAssign(self, ctx):
		value = ctx.expr(1)
		expr = ctx.expr(0)

		if isinstance(expr, ExprParser.SingleContext):
			atom = expr.atom()
			if isinstance(atom, ExprParser.IdContext):
				self.visit(value)
				self.emit(ctx, BYTE_ASSIGN_VAR, atom.ID().getText())

		elif isinstance(expr, ExprParser.IndexContext):
			self.visit(expr.expr(0)) # container
			self.visit(expr.expr(1)) # index
			self.visit(value)
			self.emit(ctx, BYTE_ASSIGN_IDX)

		elif isinstance(expr, ExprParser.AttrContext):
			self.visit(expr.expr()) # container
			self.emit(ctx, BYTE_LOADS, expr.ID().getText()) # attr
			self.visit(value)
			self.emit(ctx, BYTE_ASSIGN_IDX)

		else:
			UNREACHABLE()


	def visitCall(self, ctx):
		self.visit(ctx.expr(0))
		args = [self.visit(t) for t in ctx.expr()[1:]]
		self.emit(ctx, BYTE_CALL, len(args))

	def visitReturn(self, ctx):
		value = ctx.expr()
		if value is None:
			self.emit(ctx, BYTE_LOADB)
		else:
			self.visit(value)
		self.emit(ctx, BYTE_RETURN)


	def visitIndex(self, ctx):
		self.visit(ctx.expr(0)) # container
		self.visit(ctx.expr(1)) # index
		self.emit(ctx, BYTE_INDEX)

	def visitAttr(self, ctx):
		self.visit(ctx.expr()) # container
		self.emit(ctx, BYTE_LOADS, ctx.ID().getText()) # attr
		self.emit(ctx, BYTE_INDEX)


	def visitTernary(self, ctx):
		lelse = self.new_label()
		lend = self.new_label()

		self.visit(ctx.expr(0)) # condition
		self.emit_jump(ctx, BYTE_JUMP_FALSE, lelse)
		self.visit(ctx.expr(1)) # then
		self.emit_jump(ctx, BYTE_JUMP, lend)
		self.place_label(lelse)
		self.visit(ctx.expr(2)) # else
		self.place_label(lend)

	def visitWhile(self, ctx):
		lstart = self.new_label()
		lend = self.new_label()
		depth = self.frame_depth

		self.emit(ctx, BYTE_LOADB)
		self.emit(ctx, BYTE_TMP_PUSH)

		self.place_label(lstart)
		
		self.visit(ctx.expr(0)) # condition
		self.emit_jump(ctx, BYTE_JUMP_FALSE, lend)
		self.emit(ctx, BYTE_POP)

		self.loop_stack.append((lstart, lend, depth))
		self.visit(ctx.expr(1)) # body
		self.loop_stack.pop()

		self.emit(ctx, BYTE_TMP_SET)
		self.emit_jump(ctx, BYTE_JUMP, lstart)

		self.place_label(lend)
		self.emit(ctx, BYTE_TMP_POP)

	def visitBreak(self, ctx):
		if not self.loop_stack:
			self.error("break outside loop", ctx)

		loop = self.loop_stack[-1]
		value = ctx.expr()
		saved = self.frame_depth

		# print(loop)
		if value is not None:
			self.visit(value)
		else:
			self.emit(ctx, BYTE_LOADB)

		for i in range(self.frame_depth - loop[2]):
			self.emit(ctx, BYTE_POP_FRAME)

		self.emit_jump(ctx, BYTE_JUMP, loop[1])
		self.frame_depth = saved

	def visitContinue(self, ctx):
		if not self.loop_stack:
			self.error("continue outside loop", ctx)

		saved = self.frame_depth
		loop = self.loop_stack[-1]
		# print(loop)
		for i in range(self.frame_depth - loop[2]):
			self.emit(ctx, BYTE_POP_FRAME)

		self.emit(ctx, BYTE_TMP_LOAD)
		self.emit_jump(ctx, BYTE_JUMP, loop[0])
		self.frame_depth = saved


	def visitParen(self, ctx):
		self.visit(ctx.expr())

	def visitSingle(self, ctx):
		self.visit(ctx.atom())

	def visitInt(self, ctx):
		value = int(ctx.INT().getText())
		if -128 <= value <= 127:
			self.emit(ctx, BYTE_LOADI8, value)
		elif -32768 <= value <= 32767:
			self.emit(ctx, BYTE_LOADI16, value)
		elif -2147483658 <= value <= 2147483647:
			self.emit(ctx, BYTE_LOADI32, value)
		else:
			self.emit(ctx, BYTE_LOADI64, value)

	def visitId(self, ctx):
		self.emit(ctx, BYTE_LOAD, ctx.ID().getText())

	def visitString(self, ctx):
		value = ctx.STRING().getText()[1:-1]
		self.emit(ctx, BYTE_LOADS, value)

	def visitFloat(self, ctx):
		value = float(ctx.FLOAT().getText())
		self.emit(ctx, BYTE_LOADF64, value)

	def visitArray(self, ctx):
		vals = [self.visit(e) for e in ctx.expr()]
		self.emit(ctx, BYTE_MAKE_ARRAY, len(vals))

	def visitMap(self, ctx):
		n = 0
		for entry in ctx.entry():
			self.solve_entry(entry.atom())
			self.visit(entry.expr())
			n += 1
		self.emit(ctx, BYTE_MAKE_MAP, n)

	def visitBlock(self, ctx):
		self.emit(ctx, BYTE_PUSH_FRAME)
		self.visit_batch(ctx.expr(), ctx)
		self.emit(ctx, BYTE_POP_FRAME)




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


def parse_src(src: str, file):
	input_stream = InputStream(src)

	lexer = ExprLexer(input_stream)
	lexer.removeErrorListeners()
	lexer.addErrorListener(LangErrorListener(file, {file: src}))
	
	parser = ExprParser(CommonTokenStream(lexer))
	parser.removeErrorListeners()
	parser.addErrorListener(LangErrorListener(file, {file: src}))
	
	return parser.program()


def compile_program(tree, src, file):
	codes = [None]
	c = Compiler(file, src, codes)
	c.visit(tree)
	codes[0] = CodeObject(
		[], c.code, c.line_marks, "<main>"
	)
	return Program(codes, src, file)


def execute_vm(prog: Program, exts=None):
	vm = LangVM(prog, None, None, exts)
	return vm.run()


def parse_and_execute_src(src: str, callstack, loading, cached, file: str, srcs, exts):
	tree = parse_src(src, file)
	return ExprExecuter(callstack, loading, cached, file, srcs, exts).visit(tree)


def parse_and_execute(file_path, extensions = None):
	with open(file_path, encoding="utf-8") as file:
		src = file.read()

	rep = module_name(file_path)
	return parse_and_execute_src(src, [], [], {}, rep, {rep: src}, extensions if extensions is not None else [])
