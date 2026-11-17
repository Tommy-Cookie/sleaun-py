
import lang

with open("test/test.slea", encoding="utf-8") as file:
	src = file.read()

tree = lang.parse_src(src, "test.test")
prog = lang.compile_program(tree, src, "test.test")
lang.execute_vm(prog)
byts = lang.dump_program(prog)
with open("test/test.bin.out", "wb") as file:
	file.write(byts)
