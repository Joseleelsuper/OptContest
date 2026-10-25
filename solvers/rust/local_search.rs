use crate::core::Search;

pub fn solve(s: &mut Search) {
    let mut q = s.reference.clone();
    let mut value = s.evaluate(&q, s.n, 0);
    if s.n < 2 || value < 0 { return; }
    while s.active() {
        s.local(&mut q, value);
        if !s.active() { break; }
        s.randomize(&mut q);
        value = s.evaluate(&q, s.n, 0);
    }
}
