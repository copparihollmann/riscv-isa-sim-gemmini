# Functional baseline

This directory packages pristine public functional sources. Keep the source pins
and software ABI checks explicit. No timing observer, timing provider, compiler,
kernel implementation or guessed physical parameters belong in this package.
Generated archives and build products belong in the task's `.tmp/` directory.
