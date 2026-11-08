
from antlr4 import *
# from ExprLexer import ExprLexer
from ExprParser import ExprParser
from ExprVisitor import ExprVisitor


class ExprExecuter(ExprVisitor):
	def __init__(self):
		self.env = {"print": print}

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

		if op == "+": return lhs + rhs
		if op == "-": return lhs - rhs
		if op == "*": return lhs * rhs
		if op == "/": return lhs / rhs
		else: raise ValueError(f"UNOP {op!r}")

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
		return self.env[ctx.ID().getText()]
