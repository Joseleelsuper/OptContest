use crate::core::Search;

pub fn solve(s: &mut Search) {
    let mut q = s.reference.clone();
    if s.n < 2 { s.evaluate(&q, s.n, 0); return; }
    let mut order: Vec<usize> = (0..s.n).collect();
    let mut totals = vec![0_i64; s.n];
    for i in 0..s.n { for j in 0..s.m { totals[i] += s.p[i * s.m + j]; } }
    order.sort_by_key(|&job| totals[job]);
    let mut value = s.greedy(&mut q, 0, &order, s.n);
    if value < 0 { return; }
    s.set_initial(&q, value);
    value = s.local(&mut q, value);
    let temperature = (0.01 * s.initial_cost as f64).max(1.0);
    let mut candidate = q.clone();
    let mut removed = vec![0; s.n];
    let mut marked = vec![false; s.n];
    let count = 6.min(s.n);
    let mut stale = 0;
    while s.active() {
        let previous_best = s.best_cost;
        s.randomize(&mut order);
        marked.fill(false);
        for k in 0..count { marked[order[k]] = true; removed[k] = q[order[k]]; }
        let mut length = 0;
        for k in 0..s.n { if !marked[k] { candidate[length] = q[k]; length += 1; } }
        let mut cost = s.greedy(&mut candidate, length, &removed, count);
        if cost < 0 { break; }
        cost = s.local(&mut candidate, cost);
        if s.accept(value, cost, temperature) { q.copy_from_slice(&candidate); value = cost; }
        stale = if s.best_cost < previous_best { 0 } else { stale + 1 };
        if stale == 200 && s.active() {
            s.randomize(&mut q);
            value = s.evaluate(&q, s.n, 0);
            if value < 0 { break; }
            value = s.local(&mut q, value);
            stale = 0;
        }
    }
}
