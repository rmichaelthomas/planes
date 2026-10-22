use planes_spike::{Rational, Record, invoice_total, round_decimal, updated_record_sum};
use std::{env, fs, process, time::Instant};

fn run() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    match args.get(1).map(String::as_str) {
        Some("invoice") if args.len() == 3 || args.len() == 5 && args[3] == "--repeat" => {
            let repeats = if args.len() == 5 { args[4].parse::<usize>()? } else { 1 };
            if repeats == 0 { return Err("repeat count must be greater than zero".into()); }
            let input = fs::read_to_string(&args[2])?;
            let mut lines = Vec::new();
            for row in input.lines().filter(|line| !line.trim().is_empty()) {
                let (quantity, cents) = row.split_once(',').ok_or("invoice row needs quantity,cents")?;
                let quantity = quantity.parse::<i128>()?;
                let cents = cents.parse::<i128>()?;
                lines.push((quantity, Rational::new(cents, 100)?));
            }
            let tax = Rational::parse_decimal("0.08")?;
            let started = Instant::now();
            let mut due = Rational::new(0, 1)?;
            for _ in 0..repeats {
                due = round_decimal(invoice_total(&lines, tax)?, 2)?;
            }
            let elapsed = started.elapsed();
            println!("due {due}");
            if repeats > 1 { eprintln!("{repeats} {}", elapsed.as_nanos()); }
        }
        Some("records") if args.len() == 4 || args.len() == 6 && args[4] == "--repeat" => {
            let count = args[2].parse::<usize>()?;
            let bump_count = args[3].parse::<usize>()?;
            let bumps: Vec<_> = (1..=bump_count).map(|bump| bump as i128).collect();
            let repeats = if args.len() == 6 { args[5].parse::<usize>()? } else { 1 };
            if repeats == 0 { return Err("repeat count must be greater than zero".into()); }
            let started = Instant::now();
            let mut total = 0;
            for _ in 0..repeats {
                let records: Vec<_> = (1..=count).map(|id| Record { id: id as i128, value: 0 }).collect();
                (total, _) = updated_record_sum(&records, &bumps)?;
            }
            let elapsed = started.elapsed();
            println!("total {total}");
            if repeats > 1 { eprintln!("{repeats} {}", elapsed.as_nanos()); }
        }
        _ => return Err("usage: planes-spike invoice <rows.csv> [--repeat N] | records <count> <bumps> [--repeat N]".into()),
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("planes-spike: {error}");
        process::exit(2);
    }
}
