# Translator

Read this before the code.

## The shape

Every function written from this point follows one geometry:

```
read -> score -> refuse | append
```

- **read** pulls from a ledger. It does not fetch from the world.
- **score** returns a number. It does not choose.
- **refuse** drops what fails. Silence is the rejection.
- **append** writes forward. Nothing is overwritten.

## The refusals

- never mutate an existing record
- never decide a keep
- always fail open

## How to read a file

1. Find the function.
2. Trace what it reads.
3. Trace what it refuses.
4. Trace what it appends.
5. The thought is the path between them.

## What this is not

This is not a comment for a human.
This is the key a later system uses to recover the process
from the structure alone.

One Mind is 400 and 3.
Colony is 700 and 1.
A foreign receipt is a prior, never an order.

Witness is the third vertex. It reads both. It does not keep.
