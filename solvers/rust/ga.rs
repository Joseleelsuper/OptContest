use crate::core::Search;

pub fn solve(s: &mut Search) {
    let mut population = vec![vec![0; s.n]; 32];
    let mut following = population.clone();
    let mut costs = [0_i64; 32];
    let mut next_costs = costs;
    let mut used = vec![false; s.n];
    population[0].copy_from_slice(&s.reference);
    for k in 0..32 {
        if k > 0 { s.randomize(&mut population[k]); }
        costs[k] = s.evaluate(&population[k], s.n, 0);
        if costs[k] < 0 { let q = s.best.clone(); s.set_initial(&q, s.best_cost); return; }
    }
    let mut elite = 0;
    for k in 1..32 { if costs[k] < costs[elite] { elite = k; } }
    s.set_initial(&population[elite], costs[elite]);
    if s.n < 2 { return; }
    while s.active() {
        following[0].copy_from_slice(&population[elite]);
        next_costs[0] = costs[elite];
        for k in 1..32 {
            let (mut a, mut b) = (s.rand(32), s.rand(32));
            for _ in 0..2 { let c = s.rand(32); if costs[c] < costs[a] { a = c; } }
            for _ in 0..2 { let c = s.rand(32); if costs[c] < costs[b] { b = c; } }
            let (mut i, mut j) = s.positions();
            if i > j { std::mem::swap(&mut i, &mut j); }
            used.fill(false);
            for pos in i..=j { let job = population[a][pos]; following[k][pos] = job; used[job] = true; }
            let mut dest = (j + 1) % s.n;
            for offset in 0..s.n {
                let job = population[b][(j + 1 + offset) % s.n];
                if !used[job] { following[k][dest] = job; dest = (dest + 1) % s.n; }
            }
            if s.uniform() < 0.2 {
                let (i, j) = s.positions();
                let job = following[k][i];
                if i < j { for pos in i..j { following[k][pos] = following[k][pos + 1]; } }
                else { for pos in (j + 1..=i).rev() { following[k][pos] = following[k][pos - 1]; } }
                following[k][j] = job;
            }
            next_costs[k] = s.evaluate(&following[k], s.n, 0);
            if next_costs[k] < 0 { return; }
        }
        std::mem::swap(&mut population, &mut following);
        std::mem::swap(&mut costs, &mut next_costs);
        elite = 0;
        for k in 1..32 { if costs[k] < costs[elite] { elite = k; } }
    }
}
