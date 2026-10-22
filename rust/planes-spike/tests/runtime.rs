use planes_spike::{Rational, Record, invoice_total, round_decimal, updated_record_sum};

#[test]
fn invoice_uses_exact_decimal_inputs_and_rounds_once() {
    let items = [(2, Rational::parse_decimal("12.34").unwrap())];
    let tax_rate = Rational::parse_decimal("0.08").unwrap();
    let total = invoice_total(&items, tax_rate).unwrap();
    assert_eq!(total.to_string(), "26.6544");
    assert_eq!(round_decimal(total, 2).unwrap().to_string(), "26.65");
}

#[test]
fn decimal_rounding_uses_half_away_from_zero() {
    let positive = Rational::new(1, 8).unwrap();
    let negative = Rational::new(-1, 8).unwrap();
    assert_eq!(round_decimal(positive, 2).unwrap().to_string(), "0.13");
    assert_eq!(round_decimal(negative, 2).unwrap().to_string(), "-0.13");
}

#[test]
fn exact_decimal_parse_does_not_use_binary_float() {
    let value = Rational::parse_decimal("0.1")
        .unwrap()
        .checked_add(Rational::parse_decimal("0.2").unwrap())
        .unwrap();
    assert_eq!(value.to_string(), "0.3");
}

#[test]
fn arithmetic_overflow_is_an_error() {
    let large = Rational::new(i128::MAX, 1).unwrap();
    assert!(large.checked_add(Rational::new(1, 1).unwrap()).is_err());
}

#[test]
fn record_updates_copy_each_record_and_keep_the_original() {
    let original = vec![Record { id: 7, value: 10 }];
    let (sum, changed) = updated_record_sum(&original, &[1, 2, 3]).unwrap();
    assert_eq!(sum, 16);
    assert_eq!(original, vec![Record { id: 7, value: 10 }]);
    assert_eq!(changed, vec![Record { id: 7, value: 16 }]);
}

#[test]
fn checked_rational_handles_zero_and_normalizes_sign() {
    assert!(Rational::new(1, 0).is_err());
    assert_eq!(Rational::new(2, -4).unwrap().to_string(), "-0.5");
}
