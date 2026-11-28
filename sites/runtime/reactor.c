#define PY_SSIZE_T_CLEAN
#include <Python.h>

extern PyObject *PyInit_zlib(void);
static PyObject *dispatch;
static PyObject *answer;

/* The host can call only this fixed dispatcher. The guest has no host files. */
int lab_init(void) {
    if (PyImport_AppendInittab("zlib", PyInit_zlib) == -1) return 1;
    PyPreConfig pre;
    PyPreConfig_InitIsolatedConfig(&pre);
    pre.utf8_mode = 1;
    if (PyStatus_Exception(Py_PreInitialize(&pre))) return 2;
    PyConfig cfg;
    PyConfig_InitIsolatedConfig(&cfg);
    cfg.site_import = 0;
    cfg.write_bytecode = 0;
    cfg.install_signal_handlers = 0;
    cfg.module_search_paths_set = 1;
    PyStatus st = PyWideStringList_Append(&cfg.module_search_paths, L"/lab/lib.zip");
    if (!PyStatus_Exception(st)) st = Py_InitializeFromConfig(&cfg);
    PyConfig_Clear(&cfg);
    if (PyStatus_Exception(st)) return 3;
    PyObject *module = PyImport_ImportModule("site_dispatch");
    if (module == NULL) return 4;
    dispatch = PyObject_GetAttrString(module, "dispatch");
    Py_DECREF(module);
    return dispatch && PyCallable_Check(dispatch) ? 0 : 5;
}

const char *lab_call(const char *input, size_t length) {
    Py_CLEAR(answer);
    PyObject *args = PyBytes_FromStringAndSize(input, (Py_ssize_t)length);
    if (!args) return NULL;
    answer = PyObject_CallOneArg(dispatch, args);
    Py_DECREF(args);
    if (!answer || !PyBytes_Check(answer)) {
        PyErr_Clear();
        return NULL;
    }
    return PyBytes_AS_STRING(answer);
}

size_t lab_length(void) { return answer ? (size_t)PyBytes_GET_SIZE(answer) : 0; }
void lab_release(void) { Py_CLEAR(answer); }
