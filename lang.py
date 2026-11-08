
import sys
import lngerr
from antlr4 import *
from antlr4.error.ErrorListener import *
from ExprLexer import ExprLexer
from ExprParser import ExprParser
from ExprVisitor import ExprVisitor

add = lambda a, b: a + b
sub = lambda a, b: a - b
mul = lambda a, b: a * b
truediv = lambda a, b: a / b

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
	}
}


class ExprExecuter(ExprVisitor):
	def __init__(self, src: str):
		self.frames: list[dict] = [{"print": print}]
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


	def visitProgram(self, ctx):
		val = None
		for c in ctx.expr():
			val = self.visit(c)
		return val


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
		except:
			self.error(f"unknow infix operator {op!r}")
		
		try:
			fn = table[type(lhs)][type(rhs)]
		except:
			self.error(f"cannot apply {op!r} to {type(lhs)} and {type(rhs)}", ctx)

		return fn(lhs, rhs)

	def visitCreate(self, ctx):
		name = ctx.ID()
		value = self.visit(ctx.expr())
		print(f"create {name} := {value!r}")


	def visitCall(self, ctx):
		fn = self.visit(ctx.expr(0))
		args = [self.visit(t) for t in ctx.expr()[1:]]
		return fn(*args)


	def visitSingle(self, ctx):
		return self.visit(ctx.atom())

	def visitFloat(self, ctx):
		return float(ctx.FLOAT().getText())

	def visitInt(self, ctx):
		return int(ctx.INT().getText())

	def visitString(self, ctx):
		return ctx.STRNG().getText()[1:-1]

	def visitId(self, ctx):
		return self.get_frame_variable(ctx.ID().getText(), ctx)


class LangErrorListener(ErrorListener):
	def __init__(self, src: str):
		self.src = src

	def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
		lngerr.generic_error(f"{msg}", [(line, column + 1)], self.src)


def parse_and_execute(file_path):
	input_stream = FileStream(sys.argv[1], encoding="utf-8")

	with open(file_path, encoding="utf-8") as file:
		src = file.read()

	lexer = ExprLexer(input_stream)
	lexer.removeErrorListeners()
	lexer.addErrorListener(LangErrorListener(src))

	parser = ExprParser(CommonTokenStream(lexer))
	parser.removeErrorListeners()
	parser.addErrorListener(LangErrorListener(src))

	tree = parser.program()
	ExprExecuter(src).visit(tree)
