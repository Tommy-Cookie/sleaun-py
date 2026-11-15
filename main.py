
import lang

lang.IS_COMPILE = True
c, l, s = lang.parse_and_execute("test/test.slea")
vm = lang.LangVM(c, l, s)
vm.run()
