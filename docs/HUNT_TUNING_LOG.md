# Hunt expected-discount prior K — tuning log

Calibrated 2026-10-17T16:57:49Z by `evals/hunt/calibrate_k.py`. Model: rule of succession — expected = s/(s+K) is the predicted chance that the next member of a claim family, after s kept members, is kept too (no new information); 1-expected = K/(s+K) is the chance it brings something new (Oracle kill / revert / block). K fitted by maximum likelihood on the tuning split only.

- Split: 2026-10-17T14:08:27Z (fallback: the 2026-10-16T23:20:31Z split has no repeat-family members on its tuning side (K unidentifiable); chronological split at the 60th percentile of repeat members).
- Tuning (< 2026-10-17T14:08:27Z): 145 family-member verdicts, 3 surprises; members after a family's first: 29, surprises among them: 1.
- Fitted K = 0.10921 (log-lik -3.2298, at grid edge: False); was K = 3 (hand-set).
- Held-out: 40 verdicts, 0 surprises; members after first 20, surprises among them 0.
- Held-out predictive log-loss per verdict: fitted K 0.0084, K=3 0.2088, constant rate 0.0351 (lower is better; over members with s >= 1).
- Mean held-out expected: fitted K 0.9916, K=3 0.8119.
- Caveat: surprises are rare (single digits), so K is estimated from very few events; it is re-fitted by re-running the script, and the loader falls back to K=3 if the file is missing.
