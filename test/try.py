class A:
    a: list = []

    @classmethod
    def hook(cls, func):
        cls.a.append(func)
        return func
    
    def run(self):
        if self.a:
            for _a in self.a:
                _a()

@A.hook
def aaa():
    print("aaa...")

a = A()
@A.hook
def nbb():
    print("bbb...")
a.run()
