
import lang
import sys
sys.stdout.reconfigure(encoding="utf-8")

with open("test/test.slea", encoding="utf-8") as file:
	src = file.read()

prog = lang.compile_from("test.test")
lang.dump_into(lang.compile_from("test.a"), "test.a")

try:
	byts = lang.dump_program(prog)
	with open("test/test.bin.out", "wb") as file:
		file.write(byts)
except Exception as e:
	print(f"DUMP ERROR: {e}")

try:
	progf = lang.load_program(byts)
except Exception as e:
	print(f"LOAD ERROR: {e}")

try:
	print("PROGRAM FROM ORIGINAL COMPILER")
	lang.print_bytecode(prog)
	print("OUTPUT FROM ORIGINAL COMPILER")
	lang.execute_vm(prog)
except Exception as e:
	print(f"ERROR: {e}")

try:
	print("PROGRAM FROM DECODING THE DUMPED BINARY")
	lang.print_bytecode(progf)
	print("OUTPUT FROM DECODING THE DUMPED BINARY")
	lang.execute_vm(progf)
except Exception as e:
	print(f"ERROR: {e}")
