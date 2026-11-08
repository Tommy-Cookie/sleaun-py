
import sys
import antlr4 as ant
from ExprLexer import ExprLexer
from ExprParser import ExprParser
import lang

input_stream = ant.FileStream(sys.argv[1])
parser = ExprParser(ant.CommonTokenStream(ExprLexer(input_stream)))
tree = parser.program()

print(tree.toStringTree(recog=parser))
lang.ExprExecuter().visit(tree)
