use crate::core::Search;

pub fn solve(s: &mut Search) {
    let mut q = s.reference.clone();
    let mut candidate = q.clone();
    let mut value = s.evaluate(&q, s.n, 0);
    if s.n < 2 || value < 0 { return; }
    let initial_temperature = (0.01 * value as f64).max(1.0);
    let mut temperature = initial_temperature;
    s.set_prefix(&q, s.n);
    let mut iteration = 0_i64;
    while s.active() {
        let (i, j) = s.positions();
        s.insert(&q, &mut candidate, s.n, i, j);
        let cost = s.evaluate(&candidate, s.n, i.min(j));
        if cost < 0 { break; }
        if s.accept(value, cost, temperature) { q.copy_from_slice(&candidate); value = cost; s.set_prefix(&q, s.n); }
        iteration += 1;
        temperature *= 0.9995;
        if iteration % 10000 == 0 { temperature = initial_temperature; }
    }
}
