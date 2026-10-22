#ifndef PR31_REFERENCE_NATIVE_SYS_H
#define PR31_REFERENCE_NATIVE_SYS_H

#include <stdint.h>

/* Borrowed Goose slice ABI only. No native JSON or crypto operations. */
#pragma pack(push, 1)
typedef struct { const uint8_t *data; int64_t len; } bytes;
typedef struct { uint8_t *data; int64_t len; } mutable_bytes;
#pragma pack(pop)

#endif
