# Synthetic Receipt OCR Evaluation

- dataset: `receipt-synthetic-v1`
- manifest: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\data\receipt_synthetic\receipt-synthetic-v1\manifest.json`
- success_count: `300`
- failure_count: `0`
- use_qwen: `False`

## Summary

| metric | value |
|---|---:|
| image_count | 300 |
| vendor_name_accuracy | 0.88 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_precision_avg | 0.9444 |
| item_name_recall_avg | 0.8798 |
| item_name_f1_avg | 0.905 |
| quantity_match_rate_avg | 0.9828 |
| amount_match_rate_avg | 0.9834 |
| review_required_rate | 0.3067 |
| avg_processing_seconds | 6.7348 |
| total_elapsed_seconds | 2021.1983 |

## Layout Breakdown

### barcode_detail

| metric | value |
|---|---:|
| image_count | 60 |
| vendor_name_accuracy | 0.9 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.9271 |
| quantity_match_rate_avg | 1.0 |
| amount_match_rate_avg | 1.0 |
| review_required_rate | 0.25 |
| avg_processing_seconds | 6.5462 |

### compact_single_line

| metric | value |
|---|---:|
| image_count | 30 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.8921 |
| quantity_match_rate_avg | 0.9011 |
| amount_match_rate_avg | 0.9011 |
| review_required_rate | 0.5667 |
| avg_processing_seconds | 6.067 |

### convenience_pos

| metric | value |
|---|---:|
| image_count | 90 |
| vendor_name_accuracy | 0.6667 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.8686 |
| quantity_match_rate_avg | 0.9778 |
| amount_match_rate_avg | 0.9778 |
| review_required_rate | 0.4111 |
| avg_processing_seconds | 6.388 |

### mart_column

| metric | value |
|---|---:|
| image_count | 90 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.9386 |
| quantity_match_rate_avg | 1.0 |
| amount_match_rate_avg | 1.0 |
| review_required_rate | 0.2333 |
| avg_processing_seconds | 7.5208 |

### mixed_noise

| metric | value |
|---|---:|
| image_count | 30 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.8822 |
| quantity_match_rate_avg | 0.9933 |
| amount_match_rate_avg | 1.0 |
| review_required_rate | 0.0667 |
| avg_processing_seconds | 6.4622 |
