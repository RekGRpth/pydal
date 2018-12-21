import multiprocessing_utils

GLOBAL_LOCKER = multiprocessing_utils.SharedRLock()
THREAD_LOCAL = multiprocessing_utils.local()

DEFAULT = lambda: None

def IDENTITY(x): return x
def OR(a,b): return a|b
def AND(a,b): return a&b
