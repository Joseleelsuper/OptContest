public final class Solver {
    public static void main(String[] args) {
        String name = Core.algorithm(args);
        switch (name) {
            case "random" -> Core.run(args, RandomSearch::solve, name, false);
            case "local" -> Core.run(args, LocalSearch::solve, name, false);
            case "sa" -> Core.run(args, Sa::solve, name, false);
            case "ga" -> Core.run(args, Ga::solve, name, false);
            case "ig" -> Core.run(args, Ig::solve, name, false);
            default -> { System.err.println("Algoritmo desconocido"); System.exit(1); }
        }
    }
}
