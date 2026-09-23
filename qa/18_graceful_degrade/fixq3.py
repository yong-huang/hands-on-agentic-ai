src = open('graceful_degrade.py').read()
src = src.replace("{'✓ ≥80% (备用+缓存兜底)\" if rate >= 80 else \"✗}",
                  "{'✓ >=80% ' if rate >= 80 else 'x '}".replace('>=80% ', chr(0x2713) + ' >=80% (备用+缓存兜底) ').replace("'x '", chr(39) + chr(0x2717) + chr(39)))
src = src.replace("{'✓ 可见' if breaker.log else " + '"✗'}",
                  "{'✓ 可见' if breaker.log else " + chr(39) + chr(0x2717) + chr(39) + '})
src = src.replace('else ' + chr(39) + chr(0x2717) + chr(39) + '})", '', 0)
open('graceful_degrade.py', 'w').write(src)
