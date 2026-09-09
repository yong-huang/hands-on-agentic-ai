src = open('graceful_degrade.py').read()
src = src.replace('"(备用+缓存兜底)" if rate >= 80 else "✗"', "'(备用+缓存兜底)' if rate >= 80 else chr(10007))".replace('))', ')}'))
open('graceful_degrade.py', 'w').write(src)
