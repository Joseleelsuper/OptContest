use std::{env, fs, time::{SystemTime, UNIX_EPOCH}};

#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetProcessTimes(process: isize, created: *mut u64, exited: *mut u64, kernel: *mut u64, user: *mut u64) -> i32;
}

pub fn cpu_time() -> f64 {
    let mut times = [0_u64; 4];
    let p = times.as_mut_ptr();
    if unsafe { GetProcessTimes(-1, p, p.add(1), p.add(2), p.add(3)) } == 0 {
        panic!("GetProcessTimes failed");
    }
    (times[2] + times[3]) as f64 / 10_000_000.0
}

pub struct Search {
    pub n: usize,
    pub m: usize,
    pub p: Vec<i64>,
    prefix: Vec<i64>,
    sums: Vec<i64>,
    scratch: Vec<i64>,
    state: u64,
    pub checksum: u64,
    cpu_limit: f64,
    evaluation_limit: i64,
    pub evaluations: i64,
    stopped: bool,
    pub reference: Vec<usize>,
    pub best: Vec<usize>,
    pub initial: Vec<usize>,
    pub reference_cost: i64,
    pub best_cost: i64,
    pub initial_cost: i64,
}

impl Search {
    pub fn new(n: usize, m: usize, p: Vec<i64>, seed: u64, cpu: f64, limit: i64) -> Self {
        let mut s = Self {
            n, m, p, prefix: vec![0; (n + 1) * m], sums: vec![0; n + 1], scratch: vec![0; m],
            state: seed, checksum: 0, cpu_limit: cpu, evaluation_limit: limit, evaluations: 0, stopped: false,
            reference: vec![0; n], best: vec![0; n], initial: vec![0; n],
            reference_cost: 0, best_cost: i64::MAX, initial_cost: 0,
        };
        let mut q = vec![0; n];
        s.randomize(&mut q);
        let value = s.cost(&q, n, 0);
        s.reference.clone_from(&q); s.best.clone_from(&q); s.initial.clone_from(&q);
        s.reference_cost = value; s.best_cost = value; s.initial_cost = value;
        s
    }
    pub fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E3779B97F4A7C15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D049BB133111EB);
        z ^ (z >> 31)
    }
    pub fn rand(&mut self, bound: usize) -> usize {
        let b = bound as u64;
        let threshold = b.wrapping_neg() % b;
        loop { let value = self.next(); if value >= threshold { return (value % b) as usize; } }
    }
    pub fn uniform(&mut self) -> f64 { (self.next() >> 11) as f64 * (1.0 / 9007199254740992.0) }
    pub fn randomize(&mut self, q: &mut [usize]) {
        for (i, job) in q.iter_mut().enumerate() { *job = i; }
        for i in (1..self.n).rev() { let j = self.rand(i + 1); q.swap(i, j); }
    }
    pub fn active(&mut self) -> bool {
        if self.stopped || self.best_cost == 0 { return false; }
        if self.evaluations >= self.evaluation_limit || (self.evaluations % 32 == 0 && cpu_time() >= self.cpu_limit) {
            self.stopped = true;
        }
        !self.stopped
    }
    pub fn set_prefix(&mut self, q: &[usize], length: usize) {
        for i in 0..length {
            let mut left = 0;
            for j in 0..self.m {
                left = self.prefix[i * self.m + j].max(left) + self.p[q[i] * self.m + j];
                self.prefix[(i + 1) * self.m + j] = left;
            }
            self.sums[i + 1] = self.sums[i] + left;
        }
    }
    pub fn cost(&mut self, q: &[usize], length: usize, start: usize) -> i64 {
        self.scratch.copy_from_slice(&self.prefix[start * self.m..(start + 1) * self.m]);
        let mut total = self.sums[start];
        for i in start..length {
            let mut left = 0;
            for j in 0..self.m {
                left = self.scratch[j].max(left) + self.p[q[i] * self.m + j];
                self.scratch[j] = left;
            }
            total += left;
        }
        total
    }
    pub fn evaluate(&mut self, q: &[usize], length: usize, start: usize) -> i64 {
        if !self.active() { return -1; }
        let value = self.cost(q, length, start);
        self.evaluations += 1;
        if length == self.n {
            self.checksum = self.checksum.wrapping_add(value as u64);
            if value < self.best_cost { self.best_cost = value; self.best.copy_from_slice(q); }
        }
        value
    }
    pub fn set_initial(&mut self, q: &[usize], value: i64) {
        if value >= 0 { self.initial.copy_from_slice(q); self.initial_cost = value; }
    }
    pub fn positions(&mut self) -> (usize, usize) {
        let i = self.rand(self.n);
        let mut j = self.rand(self.n - 1);
        if j >= i { j += 1; }
        (i, j)
    }
    pub fn insert(&self, q: &[usize], out: &mut [usize], length: usize, i: usize, j: usize) {
        out[..length].copy_from_slice(&q[..length]);
        let job = q[i];
        if i < j { for k in i..j { out[k] = out[k + 1]; } }
        else { for k in (j + 1..=i).rev() { out[k] = out[k - 1]; } }
        out[j] = job;
    }
    pub fn local(&mut self, q: &mut [usize], mut value: i64) -> i64 {
        let mut candidate = vec![0; self.n];
        while self.active() {
            self.set_prefix(q, self.n);
            let mut improved = false;
            'insertion: for i in 0..self.n { for j in 0..self.n {
                if i == j { continue; }
                self.insert(q, &mut candidate, self.n, i, j);
                let cost = self.evaluate(&candidate, self.n, i.min(j));
                if cost < 0 { return value; }
                if cost < value { q.copy_from_slice(&candidate); value = cost; improved = true; break 'insertion; }
            }}
            if improved { continue; }
            'swapping: for i in 0..self.n { for j in i + 1..self.n {
                candidate.copy_from_slice(q); candidate.swap(i, j);
                let cost = self.evaluate(&candidate, self.n, i);
                if cost < 0 { return value; }
                if cost < value { q.copy_from_slice(&candidate); value = cost; improved = true; break 'swapping; }
            }}
            if !improved { break; }
        }
        value
    }
    pub fn greedy(&mut self, q: &mut [usize], mut length: usize, order: &[usize], count: usize) -> i64 {
        let mut candidate = vec![0; self.n];
        let mut chosen = vec![0; self.n];
        let mut value = -1;
        for k in 0..count {
            self.set_prefix(q, length);
            let mut minimum = i64::MAX;
            for pos in 0..=length {
                candidate[..pos].copy_from_slice(&q[..pos]); candidate[pos] = order[k];
                candidate[pos + 1..length + 1].copy_from_slice(&q[pos..length]);
                let cost = self.evaluate(&candidate, length + 1, pos);
                if cost < 0 { return -1; }
                if cost < minimum { minimum = cost; chosen[..length + 1].copy_from_slice(&candidate[..length + 1]); }
            }
            length += 1;
            q[..length].copy_from_slice(&chosen[..length]);
            value = minimum;
        }
        value
    }
    pub fn accept(&mut self, old: i64, value: i64, temperature: f64) -> bool {
        value <= old || self.uniform() < ((old - value) as f64 / temperature).exp()
    }
}

pub fn algorithm() -> String {
    let args: Vec<String> = env::args().collect();
    args.windows(2).find(|p| p[0] == "--algorithm").map(|p| p[1].clone()).unwrap_or_else(|| "ig".into())
}

fn read(path: &str) -> Result<(usize, usize, Vec<i64>), Box<dyn std::error::Error>> {
    if fs::metadata(path)?.len() > 1048576 { return Err("Archivo demasiado grande".into()); }
    let text = fs::read_to_string(path)?;
    let lines: Vec<Vec<i64>> = text.trim_start_matches('\u{feff}').lines().filter(|l| !l.trim().is_empty())
        .map(|l| l.split_whitespace().map(str::parse).collect()).collect::<Result<_, _>>()?;
    if lines.is_empty() || lines[0].len() != 2 { return Err("Cabecera esperada: n m".into()); }
    let (n, m) = (lines[0][0], lines[0][1]);
    if n < 1 || m < 1 || n > 10000 || m > 10000 || n * m > 10000 || lines.len() != (n + 1) as usize {
        return Err("Dimensiones o filas incorrectas".into());
    }
    let (n, m) = (n as usize, m as usize);
    let mut p = Vec::with_capacity(n * m);
    let mut maximum = 0;
    for row in &lines[1..] {
        if row.len() != 2 * m { return Err("Fila incorrecta".into()); }
        for j in 0..m {
            let duration = row[2 * j + 1];
            if row[2 * j] != j as i64 || duration < 0 { return Err("Par máquina-duración incorrecto".into()); }
            maximum = maximum.max(duration); p.push(duration);
        }
    }
    if maximum > i64::MAX / n as i64 / (n + m) as i64 { return Err("Posible desbordamiento int64".into()); }
    Ok((n, m, p))
}

fn sequence(q: &[usize], json: bool) -> String {
    let body = q.iter().map(|j| (j + 1).to_string()).collect::<Vec<_>>().join(if json { "," } else { " " });
    if json { format!("[{body}]") } else { body }
}

pub fn run(solve: fn(&mut Search), selected: &str, contest: bool) {
    if let Err(error) = execute(solve, selected, contest) { eprintln!("{error}"); std::process::exit(1); }
}

fn execute(solve: fn(&mut Search), selected: &str, mut contest: bool) -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().skip(1).collect();
    let mut path = String::from("test.txt");
    let mut seed = SystemTime::now().duration_since(UNIX_EPOCH)?.as_nanos() as u64 ^ std::process::id() as u64;
    let mut cpu = 57.0_f64;
    let mut limit = i64::MAX;
    let (mut has_cpu, mut has_limit) = (false, false);
    let mut i = 0;
    while i < args.len() {
        let flag = &args[i]; i += 1;
        if flag == "--contest" { contest = true; continue; }
        let value = args.get(i).ok_or("Falta el valor del argumento")?; i += 1;
        match flag.as_str() {
            "--instance" => path = value.clone(),
            "--algorithm" => if value != selected { return Err("Algoritmo incorrecto".into()); },
            "--output" => if value != "json" { return Err("Salida incorrecta".into()); },
            "--seed" => seed = value.parse()?,
            "--cpu-budget" => { cpu = value.parse()?; has_cpu = true; },
            "--max-evaluations" => { limit = value.parse()?; has_limit = true; },
            _ => return Err(format!("Argumento desconocido: {flag}").into()),
        }
    }
    if has_cpu && has_limit { return Err("Los límites son excluyentes".into()); }
    if has_limit { cpu = 86400.0; }
    if !cpu.is_finite() || cpu <= 0.0 || limit < 1 { return Err("Presupuesto incorrecto".into()); }
    let (n, m, p) = read(&path)?;
    let mut s = Search::new(n, m, p, seed, cpu, limit);
    solve(&mut s);
    if contest {
        println!("{:.10}\n{:.6}\n{}", s.best_cost as f64 / n as f64, cpu_time(), sequence(&s.best, false));
    } else {
        println!(concat!("{{\"algorithm\":\"{}\",\"seed\":{},\"reference_cost\":{},\"initial_cost\":{},\"cost\":{},",
            "\"fmed_reference\":{},\"fmed_initial\":{},\"fmed_final\":{},\"reference_sequence\":{},\"initial_sequence\":{},",
            "\"sequence\":{},\"evaluations\":{},\"cost_checksum\":{},\"cpu_seconds\":{}}}"),
            selected, seed, s.reference_cost, s.initial_cost, s.best_cost, s.reference_cost as f64 / n as f64,
            s.initial_cost as f64 / n as f64, s.best_cost as f64 / n as f64, sequence(&s.reference, true),
            sequence(&s.initial, true), sequence(&s.best, true), s.evaluations, s.checksum, cpu_time());
    }
    Ok(())
}
