def solve(n, p, i, o, formations):
  """Return minimum formation changes for POI (1-indexed p) to win."""
  beats = {('P', 'R'), ('S', 'P'), ('R', 'S')}
  counter = {'R': 'P', 'P': 'S', 'S': 'R'}
  poi = p - 1
  formations = formations.upper()

  fixed = [''] * n
  if len(formations) == n:
    fixed = list(formations)
  else:
    k = 0
    for j in range(n):
      if j != poi:
        fixed[j] = formations[k]
        k += 1

  def run(start):
    moves = []
    survivors = list(range(n))
    while len(survivors) > 1:
      nxt = []
      j = 0
      while j < len(survivors):
        if j == len(survivors) - 1:
          nxt.append(survivors[j])
          break
        a, b = survivors[j], survivors[j + 1]
        fa, fb = fixed[a], fixed[b]
        if a == poi or b == poi:
          opp = b if a == poi else a
          moves.append(counter[fixed[opp]])
          nxt.append(poi)
        elif fa == fb:
          pass
        elif (fa, fb) in beats:
          nxt.append(a)
        else:
          nxt.append(b)
        j += 2
      survivors = nxt
      if not survivors:
        return float('inf')
    if survivors != [poi]:
      return float('inf')
    cur, ch = start, 0
    for m in moves:
      if m != cur:
        ch += 1
        cur = m
    return ch

  if len(formations) == n:
    return run(fixed[poi])
  return min(run(s) for s in 'RPS')


if __name__ == '__main__':
  print(solve(3, 2, 0, 0, 'PSP'))  # example 1 -> 0
  print(solve(4, 2, 0, 0, 'PRS'))  # example 2 -> 1
