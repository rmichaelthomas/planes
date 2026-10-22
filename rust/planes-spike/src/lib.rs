//! A bounded native runtime experiment for two Planes H7 workloads.
//!
//! This is not a complete Planes interpreter. It contains only checked exact
//! rational arithmetic and immutable integer-record updates needed by the
//! invoice and record-update benchmark programs.

use std::fmt;

#[cfg(target_arch = "wasm32")]
mod wasm;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RuntimeError(&'static str);

impl fmt::Display for RuntimeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.0)
    }
}

impl std::error::Error for RuntimeError {}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rational {
    numerator: i128,
    denominator: i128,
}

impl Rational {
    pub fn new(numerator: i128, denominator: i128) -> Result<Self, RuntimeError> {
        if denominator == 0 {
            return Err(RuntimeError("a rational denominator cannot be zero"));
        }
        let (numerator, denominator) = if denominator < 0 {
            (
                numerator
                    .checked_neg()
                    .ok_or(RuntimeError("rational overflow"))?,
                denominator
                    .checked_neg()
                    .ok_or(RuntimeError("rational overflow"))?,
            )
        } else {
            (numerator, denominator)
        };
        let divisor = gcd(numerator.unsigned_abs(), denominator as u128);
        Ok(Self {
            numerator: divide_unsigned(numerator, divisor)?,
            denominator: i128::try_from((denominator as u128) / divisor)
                .map_err(|_| RuntimeError("rational overflow"))?,
        })
    }

    pub fn parse_decimal(text: &str) -> Result<Self, RuntimeError> {
        let (negative, unsigned) = match text.strip_prefix('-') {
            Some(rest) => (true, rest),
            None => (false, text.strip_prefix('+').unwrap_or(text)),
        };
        let mut parts = unsigned.split('.');
        let whole = parts.next().ok_or(RuntimeError("invalid decimal"))?;
        let fractional = parts.next().unwrap_or("");
        if parts.next().is_some()
            || whole.is_empty()
            || !whole.bytes().all(|b| b.is_ascii_digit())
            || !fractional.bytes().all(|b| b.is_ascii_digit())
        {
            return Err(RuntimeError("invalid decimal"));
        }
        let denominator = 10_i128
            .checked_pow(fractional.len() as u32)
            .ok_or(RuntimeError("decimal overflow"))?;
        let whole = whole
            .parse::<i128>()
            .map_err(|_| RuntimeError("decimal overflow"))?;
        let fraction = if fractional.is_empty() {
            0
        } else {
            fractional
                .parse::<i128>()
                .map_err(|_| RuntimeError("decimal overflow"))?
        };
        let numerator = whole
            .checked_mul(denominator)
            .and_then(|n| n.checked_add(fraction))
            .ok_or(RuntimeError("decimal overflow"))?;
        Self::new(
            if negative {
                numerator
                    .checked_neg()
                    .ok_or(RuntimeError("decimal overflow"))?
            } else {
                numerator
            },
            denominator,
        )
    }

    pub fn checked_add(self, other: Self) -> Result<Self, RuntimeError> {
        let common = gcd(self.denominator as u128, other.denominator as u128) as i128;
        let left_scale = other.denominator / common;
        let right_scale = self.denominator / common;
        let left = self
            .numerator
            .checked_mul(left_scale)
            .ok_or(RuntimeError("rational overflow"))?;
        let right = other
            .numerator
            .checked_mul(right_scale)
            .ok_or(RuntimeError("rational overflow"))?;
        let numerator = left
            .checked_add(right)
            .ok_or(RuntimeError("rational overflow"))?;
        let denominator = self
            .denominator
            .checked_mul(left_scale)
            .ok_or(RuntimeError("rational overflow"))?;
        Self::new(numerator, denominator)
    }

    pub fn checked_mul(self, other: Self) -> Result<Self, RuntimeError> {
        let cross_left = gcd(self.numerator.unsigned_abs(), other.denominator as u128);
        let cross_right = gcd(other.numerator.unsigned_abs(), self.denominator as u128);
        let left_n = divide_unsigned(self.numerator, cross_left)?;
        let right_n = divide_unsigned(other.numerator, cross_right)?;
        let left_d = i128::try_from((self.denominator as u128) / cross_right)
            .map_err(|_| RuntimeError("rational overflow"))?;
        let right_d = i128::try_from((other.denominator as u128) / cross_left)
            .map_err(|_| RuntimeError("rational overflow"))?;
        Self::new(
            left_n
                .checked_mul(right_n)
                .ok_or(RuntimeError("rational overflow"))?,
            left_d
                .checked_mul(right_d)
                .ok_or(RuntimeError("rational overflow"))?,
        )
    }

    fn rounded(self, places: u32) -> Result<Self, RuntimeError> {
        if places > 12 {
            return Err(RuntimeError(
                "rounding precision exceeds this experiment's 12-place limit",
            ));
        }
        let scale = 10_i128
            .checked_pow(places)
            .ok_or(RuntimeError("rounding overflow"))?;
        let scaled = self
            .numerator
            .checked_mul(scale)
            .ok_or(RuntimeError("rounding overflow"))?;
        let quotient = scaled / self.denominator;
        let remainder = scaled % self.denominator;
        let twice_remainder = remainder
            .unsigned_abs()
            .checked_mul(2)
            .ok_or(RuntimeError("rounding overflow"))?;
        let rounded = if twice_remainder >= self.denominator as u128 {
            quotient
                .checked_add(if scaled < 0 { -1 } else { 1 })
                .ok_or(RuntimeError("rounding overflow"))?
        } else {
            quotient
        };
        Self::new(rounded, scale)
    }
}

impl fmt::Display for Rational {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.numerator == 0 {
            return f.write_str("0");
        }
        let negative = self.numerator < 0;
        let whole = self.numerator.unsigned_abs() / self.denominator as u128;
        let mut remainder = self.numerator.unsigned_abs() % self.denominator as u128;
        let mut digits = String::new();
        for _ in 0..38 {
            if remainder == 0 {
                break;
            }
            remainder *= 10;
            digits.push(char::from(
                b'0' + (remainder / self.denominator as u128) as u8,
            ));
            remainder %= self.denominator as u128;
        }
        while digits.ends_with('0') {
            digits.pop();
        }
        if negative {
            f.write_str("-")?;
        }
        write!(f, "{whole}")?;
        if !digits.is_empty() {
            write!(f, ".{digits}")?;
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Record {
    pub id: i128,
    pub value: i128,
}

/// Sum each record after immutable copies for every `with value:` update.
pub fn updated_record_sum(
    records: &[Record],
    bumps: &[i128],
) -> Result<(i128, Vec<Record>), RuntimeError> {
    let mut updated = Vec::with_capacity(records.len());
    let mut total = 0_i128;
    for record in records {
        let mut current = *record;
        for bump in bumps {
            current = Record {
                id: current.id,
                value: current
                    .value
                    .checked_add(*bump)
                    .ok_or(RuntimeError("record value overflow"))?,
            };
        }
        total = total
            .checked_add(current.value)
            .ok_or(RuntimeError("record total overflow"))?;
        updated.push(current);
    }
    Ok((total, updated))
}

/// Compute the exact pre-rounding invoice total from quantity/price pairs.
pub fn invoice_total(
    lines: &[(i128, Rational)],
    tax_rate: Rational,
) -> Result<Rational, RuntimeError> {
    let mut total = Rational::new(0, 1)?;
    for (quantity, price) in lines {
        let subtotal = Rational::new(*quantity, 1)?.checked_mul(*price)?;
        let with_tax = subtotal.checked_add(subtotal.checked_mul(tax_rate)?)?;
        total = total.checked_add(with_tax)?;
    }
    Ok(total)
}

pub fn round_decimal(value: Rational, places: u32) -> Result<Rational, RuntimeError> {
    value.rounded(places)
}

pub fn invoice_csv(input: &str, tax_rate: Rational) -> Result<Rational, RuntimeError> {
    let mut lines = Vec::new();
    for row in input.lines().filter(|line| !line.trim().is_empty()) {
        let (quantity, cents) = row
            .split_once(',')
            .ok_or(RuntimeError("invoice row needs quantity,cents"))?;
        let quantity = quantity
            .parse::<i128>()
            .map_err(|_| RuntimeError("invalid invoice quantity"))?;
        let cents = cents
            .parse::<i128>()
            .map_err(|_| RuntimeError("invalid invoice cents"))?;
        lines.push((quantity, Rational::new(cents, 100)?));
    }
    round_decimal(invoice_total(&lines, tax_rate)?, 2)
}

pub fn record_workload(count: usize, bump_count: usize) -> Result<i128, RuntimeError> {
    let records: Vec<_> = (1..=count)
        .map(|id| Record {
            id: id as i128,
            value: 0,
        })
        .collect();
    let bumps: Vec<_> = (1..=bump_count).map(|bump| bump as i128).collect();
    updated_record_sum(&records, &bumps).map(|(sum, _)| sum)
}

fn gcd(mut left: u128, mut right: u128) -> u128 {
    while right != 0 {
        let remainder = left % right;
        left = right;
        right = remainder;
    }
    left.max(1)
}

fn divide_unsigned(value: i128, divisor: u128) -> Result<i128, RuntimeError> {
    if divisor == (1_u128 << 127) {
        return if value == i128::MIN {
            Ok(-1)
        } else {
            Err(RuntimeError("rational overflow"))
        };
    }
    Ok(value / i128::try_from(divisor).map_err(|_| RuntimeError("rational overflow"))?)
}
