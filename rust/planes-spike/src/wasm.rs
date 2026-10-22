use crate::{Rational, invoice_csv, record_workload};
const INPUT_CAPACITY: usize = 512 * 1024;
const OUTPUT_CAPACITY: usize = 128;

static mut INPUT: [u8; INPUT_CAPACITY] = [0; INPUT_CAPACITY];
static mut OUTPUT: [u8; OUTPUT_CAPACITY] = [0; OUTPUT_CAPACITY];

#[unsafe(no_mangle)]
pub extern "C" fn planes_input_ptr() -> usize {
    std::ptr::addr_of_mut!(INPUT).cast::<u8>() as usize
}

#[unsafe(no_mangle)]
pub extern "C" fn planes_input_capacity() -> usize {
    INPUT_CAPACITY
}

#[unsafe(no_mangle)]
pub extern "C" fn planes_invoice(input_len: usize) -> u64 {
    let input = unsafe {
        let ptr = std::ptr::addr_of!(INPUT).cast::<u8>();
        std::slice::from_raw_parts(ptr, input_len.min(INPUT_CAPACITY))
    };
    let result = std::str::from_utf8(input)
        .map_err(|_| "input is not UTF-8".to_owned())
        .and_then(|text| {
            invoice_csv(text, Rational::new(8, 100).expect("valid tax rate"))
                .map(|due| format!("due {due}"))
                .map_err(|error| error.to_string())
        });
    write_output(result)
}

#[unsafe(no_mangle)]
pub extern "C" fn planes_records(count: usize, bump_count: usize) -> u64 {
    let result = record_workload(count, bump_count)
        .map(|total| format!("total {total}"))
        .map_err(|error| error.to_string());
    write_output(result)
}

fn write_output(result: Result<String, String>) -> u64 {
    let text = result.unwrap_or_else(|error| format!("error {error}"));
    let bytes = text.as_bytes();
    let cursor = bytes.len().min(OUTPUT_CAPACITY);
    unsafe {
        let output = std::ptr::addr_of_mut!(OUTPUT).cast::<u8>();
        std::ptr::copy_nonoverlapping(bytes.as_ptr(), output, cursor);
        ((output as u32 as u64) << 32) | cursor as u64
    }
}
