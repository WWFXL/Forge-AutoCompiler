/* 当前平台功能探针：直接调用与 libffi 调用使用同一组已知答案。 */
#include <ffi.h>
#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct { int number; double value; } Pair;
static int add(int a, int b) { return a + b; }
static double mix(double a, double b) { return a * 2.0 + b; }
static Pair transform(Pair p) { Pair r = {p.number + 3, p.value * 2.0}; return r; }
static double sum(int n, ...) {
    va_list ap; double r = 0; va_start(ap, n);
    for (int i = 0; i < n; ++i) r += va_arg(ap, double);
    va_end(ap); return r;
}
static void callback(ffi_cif *cif, void *ret, void **args, void *userdata) {
    (void)cif;
    *(int *)ret = *(int *)args[0] + *(int *)args[1] + *(int *)userdata;
}
static void require(int ok, const char *name) {
    if (!ok) { fprintf(stderr, "FAIL %s\n", name); exit(1); }
    printf("PASS %s\n", name);
}
int main(void) {
    ffi_cif cif;
    ffi_type *integers[] = { &ffi_type_sint32, &ffi_type_sint32 };
    int a = -7, b = 19;
    void *iargs[] = { &a, &b };
    ffi_arg ir = 0;
    require(ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 2, &ffi_type_sint32, integers) == FFI_OK,
            "prepare_integer");
    ffi_call(&cif, FFI_FN(add), &ir, iargs);
    require((int)ir == add(a, b), "integer_call");

    ffi_type *doubles[] = { &ffi_type_double, &ffi_type_double };
    double x = 1.25, y = -0.5, dr = 0;
    void *dargs[] = { &x, &y };
    require(ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 2, &ffi_type_double, doubles) == FFI_OK,
            "prepare_double");
    ffi_call(&cif, FFI_FN(mix), &dr, dargs);
    require(fabs(dr - mix(x, y)) < 1e-12, "floating_call");

    ffi_type *members[] = { &ffi_type_sint32, &ffi_type_double, NULL };
    ffi_type pair = { 0, 0, FFI_TYPE_STRUCT, members };
    ffi_type *structs[] = { &pair };
    Pair input = { 4, 1.75 }, result = { 0, 0 }, expected = transform(input);
    void *sargs[] = { &input };
    require(ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 1, &pair, structs) == FFI_OK,
            "prepare_struct");
    ffi_call(&cif, FFI_FN(transform), &result, sargs);
    require(result.number == expected.number && fabs(result.value - expected.value) < 1e-12,
            "struct_argument_and_return");

    int count = 3;
    double v1 = 1.5, v2 = 2.25, v3 = -0.75;
    ffi_type *var_types[] = { &ffi_type_sint32, &ffi_type_double,
                              &ffi_type_double, &ffi_type_double };
    void *vargs[] = { &count, &v1, &v2, &v3 };
    require(ffi_prep_cif_var(&cif, FFI_DEFAULT_ABI, 1, 4, &ffi_type_double, var_types) == FFI_OK,
            "prepare_variadic");
    ffi_call(&cif, FFI_FN(sum), &dr, vargs);
    require(fabs(dr - sum(count, v1, v2, v3)) < 1e-12, "variadic_call");

    int extra = 5;
    void *code = NULL;
    ffi_closure *closure = ffi_closure_alloc(sizeof(ffi_closure), &code);
    require(closure != NULL && code != NULL, "allocate_closure");
    require(ffi_prep_cif(&cif, FFI_DEFAULT_ABI, 2, &ffi_type_sint32, integers) == FFI_OK,
            "prepare_callback_cif");
    require(ffi_prep_closure_loc(closure, &cif, callback, &extra, code) == FFI_OK,
            "prepare_closure");
    int (*fn)(int, int) = (int (*)(int, int))code;
    require(fn(a, b) == add(a, b) + extra, "closure_callback");
    ffi_closure_free(closure);
    puts("FUNCTIONAL_SCENARIOS=5 PASSED=5");
    return 0;
}
