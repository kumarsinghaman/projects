def solve(n, poi, formations):
  win = {'R': 'P', 'P': 'S', 'S': 'R'}
  beat = {('P', 'R'), ('S', 'P'), ('R', 'S')}
  poi -= 1
  f = formations.upper()

  fixed = list(f) if len(f) == n else [''] * n
  if len(f) != n:
    k = 0
    for i in range(n):
      if i != poi:
        fixed[i] = f[k]
        k += 1

  def count(start):
    need, alive = [], list(range(n))
    while len(alive) > 1:
      nxt, i = [], 0
      while i < len(alive):
        if i == len(alive) - 1:
          nxt.append(alive[i])
          break
        a, b = alive[i], alive[i + 1]
        if a == poi or b == poi:
          need.append(win[fixed[b if a == poi else a]])
          nxt.append(poi)
        elif fixed[a] == fixed[b]:
          pass
        elif (fixed[a], fixed[b]) in beat:
          nxt.append(a)
        else:
          nxt.append(b)
        i += 2
      alive = nxt
    if alive != [poi]:
      return 10**9
    ans, cur = 0, start
    for m in need:
      if m != cur:
        ans += 1
        cur = m
    return ans

  return count(fixed[poi]) if len(f) == n else min(count(s) for s in 'RPS')
