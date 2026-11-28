#!/usr/bin/env bash
set -euo pipefail
sdk=$1
cpy=$2
lib=$3
zlib=$4
out=$5
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT
cc="$sdk/bin/clang"

for unit in adler32 compress crc32 deflate infback inffast inflate inftrees trees uncompr zutil; do
  "$cc" -Oz -I"$zlib" -c "$zlib/$unit.c" -o "$dir/zlib_$unit.o"
done
"$cc" -Oz -DPy_BUILD_CORE_MODULE -I"$lib" -I"$cpy/Include" -I"$cpy/Include/internal" -I"$zlib" \
  -c "$cpy/Modules/zlibmodule.c" -o "$dir/python_zlib.o"
"$cc" -Oz -I"$lib" -I"$cpy/Include" -c "$(dirname "$0")/../runtime/reactor.c" -o "$dir/reactor.o"

"$cc" -mexec-model=reactor "$dir/"*.o \
  "$lib/libpython3.13.a" "$lib/Modules/_decimal/libmpdec/libmpdec.a" \
  "$lib/Modules/_hacl/libHacl_Hash_SHA2.a" "$lib/Modules/expat/libexpat.a" \
  -ldl -lwasi-emulated-signal -lwasi-emulated-process-clocks -lwasi-emulated-getpid \
  -Wl,-z,stack-size=1048576 -Wl,--max-memory=50331648 -Wl,--strip-all \
  -Wl,--export=lab_init,--export=lab_call,--export=lab_length,--export=lab_release \
  -Wl,--export=malloc,--export=free -o "$out"
