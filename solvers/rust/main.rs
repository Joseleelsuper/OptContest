mod core;
mod random_search;
mod local_search;
mod sa;
mod ga;
mod ig;

fn main() {
    let name = core::algorithm();
    let solve: fn(&mut core::Search) = match name.as_str() {
        "random" => random_search::solve, "local" => local_search::solve, "sa" => sa::solve,
        "ga" => ga::solve, "ig" => ig::solve,
        _ => { eprintln!("Algoritmo desconocido"); std::process::exit(1); },
    };
    core::run(solve, &name, false);
}
