import json, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
d = json.load(open("hl.json"))["rows"]; n = [r["n"] for r in d]
fig, ax = plt.subplots(1, 2, figsize=(11, 4.2))
ax[0].semilogy(n, [r["a"] for r in d], "o-", label="actual a(n) (computed)")
ax[0].semilogy(n, [r["hl_consecutive"] for r in d], "s--", label="HL consecutive (incl.-excl.)")
ax[0].semilogy(n, [r["hl_tuple_only"] for r in d], "^:", label="HL tuple only (no consecutiveness)")
ax[0].set_xlabel("n  (first 2·10^n primes)"); ax[0].set_ylabel("count"); ax[0].legend(); ax[0].set_title("A104062: actual vs Hardy–Littlewood")
ax[1].plot(n, [r["actual_over_consecutive"] for r in d], "o-", label="actual / HL consecutive")
ax[1].plot(n, [r["actual_over_tuple"] for r in d], "^:", label="actual / HL tuple only")
ax[1].axhline(1, color="gray", lw=.8); ax[1].set_xlabel("n"); ax[1].set_ylim(0, 1.1); ax[1].legend(); ax[1].set_title("ratio (HL is a conjecture)")
fig.tight_layout(); fig.savefig("a104062_actual_vs_hl.png", dpi=130)
