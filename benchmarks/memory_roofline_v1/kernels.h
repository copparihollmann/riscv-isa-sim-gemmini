#pragma once
#include <stddef.h>
#include <stdint.h>
enum { READ_SUM, WRITE, COPY, TRIAD, CHASE, PANEL, SCALAR_SUM };
uint64_t roof_kernel(unsigned kind, unsigned char *a, unsigned char *b,
                     unsigned char *c, size_t bytes, unsigned repeats,
                     size_t pitch, size_t rows);
