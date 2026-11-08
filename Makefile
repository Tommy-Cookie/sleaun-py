
ANTLR := D:/ANTLR/antlr-4.13.2-complete.jar
ANTLR_OBJ := grammar/Expr.g4

PY_MAIN := main.py
FILE_IN := test.txt

all:
	java -jar $(ANTLR) -Dlanguage=Python3 $(ANTLR_OBJ) -visitor
	py $(PY_MAIN) $(FILE_IN)
