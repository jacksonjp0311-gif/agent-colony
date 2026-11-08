# OEIS conjecture results for James's review

Machine results only. Nothing here has been authorized, submitted to OEIS or posted. Each needs a human check of the parse, the b-file and the literature.

## A212205 — proved_checked (cycle 20261107T235553Z_34e22b)
OEIS text (formula): "Conjecture D-finite with recurrence: (n+1)*a(n) +2*(n-1)*a(n-1) +6*(-2*n+1)*a(n-2) +12*(-2*n+5)*a(n-3) +(37*n-77)*a(n-4) +2*(37*n-151)*a(n-5) +6*(-n+5)*a(n-6) +12*(-n+7)*a(n-7)=0. - _R. J. Mathar_, Aug 20 2018"
Parsed claim: `{"form": "relation", "parts": ["(n+1)*a(n)+2*(n-1)*a(n-1)+6*(-2*n+1)*a(n-2)+12*(-2*n+5)*a(n-3)+(37*n-77)*a(n-4)+2*(37*n-151)*a(n-5)+6*(-n+5)*a(n-6)+12*(-n+7)*a(n-7)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 6 with zero radical part; recurrence holds for n >= 7 by the operator identity and is checked directly on 0..6

## A102882 — proved_checked (cycle 20261107T235553Z_34e22b)
OEIS text (formula): "Conjecture: n*(n+1)*a(n) +2*(2*n+3)*(n-1)*a(n-1) +2*(n^2-7)*a(n-2) +6*(5+n-2*n^2)*a(n-3) -15*(n+2)*(n-3)*a(n-4)=0. - _R. J. Mathar_, Nov 09 2012"
Parsed claim: `{"form": "relation", "parts": ["n*(n+1)*a(n)+2*(2*n+3)*(n-1)*a(n-1)+2*(n^2-7)*a(n-2)+6*(5+n-2*n^2)*a(n-3)-15*(n+2)*(n-3)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree -1 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A166078 — proved_checked (cycle 20261107T235553Z_34e22b)
OEIS text (formula): "Conjecture: n*a(n) + 2*(2*n-5)*a(n-1) + (34-19*n)*a(n-2) + 14*(n-2)*a(n-3)=0. - _R. J. Mathar_, Nov 14 2011"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+2*(2*n-5)*a(n-1)+(34-19*n)*a(n-2)+14*(n-2)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 1 with zero radical part; recurrence holds for n >= 3 by the operator identity and is checked directly on 0..2

## A166076 — proved_checked (cycle 20261107T235901Z_5fdebf)
OEIS text (formula): "Conjecture: 3*(n)*a(n) +5*(-5*n+9)*a(n-1) +69*(-n+2)*a(n-2) +5*(-11*n+27)*a(n-3) +14*(-n+3)*a(n-4)=0. - _R. J. Mathar_, Feb 10 2015"
Parsed claim: `{"form": "relation", "parts": ["3*(n)*a(n)+5*(-5*n+9)*a(n-1)+69*(-n+2)*a(n-2)+5*(-11*n+27)*a(n-3)+14*(-n+3)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 2 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A115967 — proved_checked (cycle 20261107T235901Z_5fdebf)
OEIS text (formula): "Conjecture: 3*n*a(n) + (-14*n+9)*a(n-1) + (-5*n+3)*a(n-2) + 12*(4*n-9)* a(n-3) + 36*(n-3)*a(n-4) = 0. - _R. J. Mathar_, Nov 15 2012"
Parsed claim: `{"form": "relation", "parts": ["3*n*a(n)+(-14*n+9)*a(n-1)+(-5*n+3)*a(n-2)+12*(4*n-9)*a(n-3)+36*(n-3)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 2 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A162479 — proved_checked (cycle 20261107T235901Z_5fdebf)
OEIS text (formula): "Conjecture D-finite with recurrence: n*a(n) +3*(2-3n)*a(n-1) +2*(7n-13)*a(n-2)+2*(12-5n)*a(n-3) +(5n-16)*a(n-4) +(4-n)*a(n-5)=0. - _R. J. Mathar_, Nov 17 2011"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+3*(2-3*n)*a(n-1)+2*(7*n-13)*a(n-2)+2*(12-5*n)*a(n-3)+(5*n-16)*a(n-4)+(4-n)*a(n-5)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree -1 with zero radical part; recurrence holds for n >= 5 by the operator identity and is checked directly on 0..4

## A247170 — proved_checked (cycle 20261107T235901Z_5fdebf)
OEIS text (formula): "Conjectured: +n*(2*n-7)*a(n) +(n-1)*(2*n-9)*a(n-1) +2*(-2*n^2+9*n-6)*a(n-2) +2*(-6*n^2+33*n-38)*a(n-3) +3*(-2*n^2+15*n-26)*a(n-4) +(2*n-5)*(n-5)*a(n-5) = 0."
Parsed claim: `{"form": "relation", "parts": ["+n*(2*n-7)*a(n)+(n-1)*(2*n-9)*a(n-1)+2*(-2*n^2+9*n-6)*a(n-2)+2*(-6*n^2+33*n-38)*a(n-3)+3*(-2*n^2+15*n-26)*a(n-4)+(2*n-5)*(n-5)*a(n-5)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 4 with zero radical part; recurrence holds for n >= 6 by the operator identity and is checked directly on 1..5

## A239201 — proved_checked (cycle 20261108T000129Z_678dd4)
OEIS text (formula): "Conjecture D-finite with recurrence: (-n+1)*a(n) +(7*n-11)*a(n-1) +(-11*n+25)*a(n-2) +5*(n-3)*a(n-3)=0. - _R. J. Mathar_, Oct 07 2016"
Parsed claim: `{"form": "relation", "parts": ["(-n+1)*a(n)+(7*n-11)*a(n-1)+(-11*n+25)*a(n-2)+5*(n-3)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 2 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 1..3

## A116409 — proved_checked (cycle 20261108T000129Z_678dd4)
OEIS text (formula): "Conjecture: n*a(n) +2*(-3*n+2)*a(n-1) +2*(4*n-5)*a(n-2) +6*(n-2)*a(n-3) +9*(-n+2)*a(n-4)=0. - _R. J. Mathar_, Nov 11 2014"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+2*(-3*n+2)*a(n-1)+2*(4*n-5)*a(n-2)+6*(n-2)*a(n-3)+9*(-n+2)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 3 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A174783 — proved_checked (cycle 20261108T000129Z_678dd4)
OEIS text (formula): "Conjecture: n*a(n) -2*a(n-1) +(8-5*n)*a(n-2) +2*a(n-3) +4*(n-2)*a(n-4)=0. - _R. J. Mathar_, Nov 13 2012"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)-2*a(n-1)+(8-5*n)*a(n-2)+2*a(n-3)+4*(n-2)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 1 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A104625 — proved_checked (cycle 20261108T050957Z_fbd393)
OEIS text (formula): "Conjecture: n*a(n) + (n-3)*a(n-1) + 2*(-28*n+51)*a(n-2) + 72*(2*n-5)*a(n-3) - n*a(n-4) + (-5*n+3)*a(n-5) + 18*(2*n-5)*a(n-6) = 0. - _R. J. Mathar_, Feb 20 2015"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+(n-3)*a(n-1)+2*(-28*n+51)*a(n-2)+72*(2*n-5)*a(n-3)-n*a(n-4)+(-5*n+3)*a(n-5)+18*(2*n-5)*a(n-6)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 4 with zero radical part; recurrence holds for n >= 6 by the operator identity and is checked directly on 0..5

## A025577 — proved_checked (cycle 20261108T050957Z_fbd393)
OEIS text (formula): "Conjecture: (-n+1)*a(n) +3*(n-1)*a(n-1) +(n-7)*a(n-2) +3*(-n+3)*a(n-3)=0. - _R. J. Mathar_, Jul 02 2018"
Parsed claim: `{"form": "relation", "parts": ["(-n+1)*a(n)+3*(n-1)*a(n-1)+(n-7)*a(n-2)+3*(-n+3)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree -1 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 1..3

## A242781 — proved_checked (cycle 20261108T050957Z_fbd393)
OEIS text (formula): "Conjecture D-finite with recurrence: 3*(n+1)*a(n) -18*n*a(n-1) +2*(11*n-13)*a(n-2) +6*(n-7)*a(n-3) +(7*n-9)*a(n-4) +2*(2*n-7)*a(n-5)=0. - _R. J. Mathar_, Jan 25 2020"
Parsed claim: `{"form": "relation", "parts": ["3*(n+1)*a(n)-18*n*a(n-1)+2*(11*n-13)*a(n-2)+6*(n-7)*a(n-3)+(7*n-9)*a(n-4)+2*(2*n-7)*a(n-5)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 4 with zero radical part; recurrence holds for n >= 5 by the operator identity and is checked directly on 0..4

## A103973 — proved_checked (cycle 20261108T051234Z_bc2b54)
OEIS text (formula): "Conjecture D-finite with recurrence: 11*n*(n+1)*a(n)+4*n*(4*n+1)*a(n-1) +8*(27-11*n^2)*a(n-2) -32*(4*n+9)*(n-3)*a(n-3)=0. - _R. J. Mathar_, Nov 09 2012"
Parsed claim: `{"form": "relation", "parts": ["11*n*(n+1)*a(n)+4*n*(4*n+1)*a(n-1)+8*(27-11*n^2)*a(n-2)-32*(4*n+9)*(n-3)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 2 with zero radical part; recurrence holds for n >= 3 by the operator identity and is checked directly on 0..2

## A097332 — proved_checked (cycle 20261108T051234Z_bc2b54)
OEIS text (formula): "Conjecture D-finite with recurrence: (n+1)*a(n) - 3*n*a(n-1) + (-n+5)*a(n-2) + 3*(n-2)*a(n-3) = 0. - _R. J. Mathar_, Nov 26 2012"
Parsed claim: `{"form": "relation", "parts": ["(n+1)*a(n)-3*n*a(n-1)+(-n+5)*a(n-2)+3*(n-2)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 1 with zero radical part; recurrence holds for n >= 3 by the operator identity and is checked directly on 0..2

## A234269 — proved_checked (cycle 20261108T051234Z_bc2b54)
OEIS text (formula): "Conjecture D-finite with recurrence: -(n+1)*(2*n-5)*a(n) -2*n*(n-4)*a(n-1) +4*(n-1)*(2*n-3)*a(n-2) +2*(8*n^2-32*n+29)*a(n-3) +4*(n-2)*(2*n-7)*a(n-4)=0. - _R. J. Mathar_, Jan 24 2020"
Parsed claim: `{"form": "relation", "parts": ["-(n+1)*(2*n-5)*a(n)-2*n*(n-4)*a(n-1)+4*(n-1)*(2*n-3)*a(n-2)+2*(8*n^2-32*n+29)*a(n-3)+4*(n-2)*(2*n-7)*a(n-4)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 3 with zero radical part; recurrence holds for n >= 4 by the operator identity and is checked directly on 0..3

## A244886 — proved_checked (cycle 20261108T051234Z_bc2b54)
OEIS text (formula): "Conjecture D-finite with recurrence: n*a(n) +(-5*n+3)*a(n-1) +2*(n)*a(n-2) +(13*n-30)*a(n-3) +3*(-1)*a(n-4) +(-8*n+21)*a(n-5) +3*(-n+3)*a(n-6)=0. - _R. J. Mathar_, Jan 24 2020"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+(-5*n+3)*a(n-1)+2*(n)*a(n-2)+(13*n-30)*a(n-3)+3*(-1)*a(n-4)+(-8*n+21)*a(n-5)+3*(-n+3)*a(n-6)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 4 with zero radical part; recurrence holds for n >= 6 by the operator identity and is checked directly on 0..5

## A128057 — proved_checked (cycle 20261108T051451Z_4cf845)
OEIS text (formula): "Conjecture: n*(5*n-9)*a(n) +4*a(n-1) +4*(5*n-4)*(n-2)*a(n-2)=0. - _R. J. Mathar_, Dec 02 2014"
Parsed claim: `{"form": "relation", "parts": ["n*(5*n-9)*a(n)+4*a(n-1)+4*(5*n-4)*(n-2)*a(n-2)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree -1 with zero radical part; recurrence holds for n >= 2 by the operator identity and is checked directly on 0..1

## A097331 — proved_checked (cycle 20261108T051451Z_4cf845)
OEIS text (formula): "Conjecture: (n+1)*a(n) + n*a(n-1) + 4*(-n+2)*a(n-2) + 4*(-n+3)*a(n-3)=0. - _R. J. Mathar_, Dec 02 2012"
Parsed claim: `{"form": "relation", "parts": ["(n+1)*a(n)+n*a(n-1)+4*(-n+2)*a(n-2)+4*(-n+3)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 2 with zero radical part; recurrence holds for n >= 3 by the operator identity and is checked directly on 0..2

## A240688 — proved_checked (cycle 20261108T051451Z_4cf845)
OEIS text (formula): "Conjecture: n*(n-1)*a(n) -(3*n-2)*(n-1)*a(n-1) +2*(-4*n^2+7*n-1)*a(n-2) -4*n*(n-2)*a(n-3)=0. - _R. J. Mathar_, Jun 14 2016"
Parsed claim: `{"form": "relation", "parts": ["n*(n-1)*a(n)-(3*n-2)*(n-1)*a(n-1)+2*(-4*n^2+7*n-1)*a(n-2)-4*n*(n-2)*a(n-3)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree -1 with zero radical part; recurrence holds for n >= 3 by the operator identity and is checked directly on 0..2

## A116391 — proved_checked (cycle 20261108T062345Z_b8d152)
OEIS text (formula): "Conjecture D-finite with recurrence: n*a(n) +(n)*a(n-1) +3*(-3*n+4)*a(n-2) +3*(-3*n+4)*a(n-3) +20*(n-3)*a(n-4) +20*(n-3)*a(n-5)=0. - _R. J. Mathar_, Jan 23 2020"
Parsed claim: `{"form": "relation", "parts": ["n*a(n)+(n)*a(n-1)+3*(-3*n+4)*a(n-2)+3*(-3*n+4)*a(n-3)+20*(n-3)*a(n-4)+20*(n-3)*a(n-5)", "0"], "rels": ["="], "mod": null, "n0": null}`
Checker: x-side residual is a polynomial of degree 1 with zero radical part; recurrence holds for n >= 5 by the operator identity and is checked directly on 0..4
