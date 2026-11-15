
import lang

lang.IS_COMPILE = True
c = lang.parse_and_execute("test/test.slea")
vm = lang.LangVM(c)
vm.run()
