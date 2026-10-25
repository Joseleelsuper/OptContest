use crate::core::Search;

pub fn solve(s: &mut Search) {
    let mut q = s.reference.clone();
    s.evaluate(&q, s.n, 0);
    if s.n < 2 { return; }
    while s.active() { s.randomize(&mut q); s.evaluate(&q, s.n, 0); }
}
