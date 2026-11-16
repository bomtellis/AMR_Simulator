#include <Python.h>
#include <limits.h>
#include "corridor_timing.h"

struct PythonRows {
    PyObject *list;
    mutable int count;

    explicit PythonRows(PyObject *rows) : list(rows), count(0) {
        if (!rows) return;
        if (!PyList_Check(rows)) {
            PyErr_SetString(PyExc_TypeError, "Corridor reservation rows must be a list");
            return;
        }
        const Py_ssize_t size = PyList_GET_SIZE(rows);
        if (size > INT_MAX) {
            PyErr_SetString(PyExc_OverflowError, "Too many corridor reservation intervals");
            return;
        }
        count = static_cast<int>(size);
    }

    int size() const { return count; }
    double get(int index, int column) const {
        PyObject *row = PyList_GET_ITEM(list, index);
        if (!PyTuple_Check(row) || PyTuple_GET_SIZE(row) < 2) {
            count = 0;
            PyErr_SetString(PyExc_TypeError, "A corridor reservation needs start and end times");
            return 0.;
        }
        PyObject *value = PyTuple_GET_ITEM(row, column);
        if (PyFloat_CheckExact(value)) return PyFloat_AS_DOUBLE(value);
        const double number = PyFloat_AsDouble(value);
        if (PyErr_Occurred()) count = 0;
        return number;
    }
    double start(int index) const { return get(index, 0); }
    double end(int index) const { return get(index, 1); }
};

static double max_duration(PyObject *mapping, PyObject *key) {
    PyObject *value = PyDict_GetItemWithError(mapping, key);
    return value ? PyFloat_AsDouble(value) : 0.;
}

struct SegmentKeys {
    PyObject *duration, *speed_factor, *congestion_count;
};

static bool put(PyObject *record, PyObject *name, PyObject *value) {
    if (!value) return false;
    const bool success = PyDict_SetItem(record, name, value) == 0;
    Py_DECREF(value);
    return success;
}

static bool append(PyObject *segments, PyObject *record) {
    if (!record) return false;
    const bool success = PyList_Append(segments, record) == 0;
    Py_DECREF(record);
    return success;
}

static PyObject *evaluate(PyObject *module, PyObject *args) {
    const auto *keys = static_cast<SegmentKeys *>(PyModule_GetState(module));
    PyObject *path, *physical, *directed, *nodes, *physical_max, *directed_max, *node_max;
    double current, spacing, window, slowdown, min_factor;
    int collect;
    if (!PyArg_ParseTuple(args, "O!O!O!O!O!O!O!dddddp", &PyList_Type, &path,
                          &PyDict_Type, &physical, &PyDict_Type, &directed, &PyDict_Type, &nodes,
                          &PyDict_Type, &physical_max, &PyDict_Type, &directed_max, &PyDict_Type,
                          &node_max, &current, &spacing, &window, &slowdown, &min_factor, &collect))
        return nullptr;
    PyObject *segments = PyList_New(0);
    if (!segments) return nullptr;
    double total = 0.;
    for (Py_ssize_t i = 0; i < PyList_GET_SIZE(path); ++i) {
        if (!__builtin_isfinite(current)) {
            Py_DECREF(segments);
            Py_RETURN_NONE;
        }
        PyObject *edge = PyList_GET_ITEM(path, i);
        if (!PyTuple_Check(edge) || PyTuple_GET_SIZE(edge) != 7) {
            PyErr_SetString(PyExc_TypeError, "Expected a prepared corridor edge");
            goto error;
        }
        PyObject *origin = PyTuple_GET_ITEM(edge, 0);
        PyObject *destination = PyTuple_GET_ITEM(edge, 1);
        PyObject *directed_key = PyTuple_GET_ITEM(edge, 2);
        PyObject *physical_key = PyTuple_GET_ITEM(edge, 3);
        PyObject *base_value = PyTuple_GET_ITEM(edge, 4);
        const double base = PyFloat_CheckExact(base_value) ? PyFloat_AS_DOUBLE(base_value) : PyFloat_AsDouble(base_value);
        const long lane_count = PyLong_AsLong(PyTuple_GET_ITEM(edge, 5));
        if (lane_count < 1 || lane_count > INT_MAX) {
            if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, "Invalid corridor lane count");
            goto error;
        }
        const int lanes = static_cast<int>(lane_count);
        const PythonRows p{PyDict_GetItemWithError(physical, physical_key)};
        const PythonRows d{PyDict_GetItemWithError(directed, directed_key)};
        const PythonRows n{PyDict_GetItemWithError(nodes, destination)};
        if (PyErr_Occurred()) goto error;
        const TimingStep step = time_edge(
            p, d, n, p.size() ? max_duration(physical_max, physical_key) : 0.,
            d.size() ? max_duration(directed_max, directed_key) : 0.,
            n.size() ? max_duration(node_max, destination) : 0.,
            current, base, spacing, lanes, window, slowdown, min_factor);
        if (PyErr_Occurred()) goto error;
        current = step.finish;
        if (step.edge_wait > 0.) {
            total += step.edge_wait;
            if (collect && !append(segments, Py_BuildValue(
                    "{s:s,s:O,s:O,s:d,s:d,s:i,s:i}", "type", "wait_for_edge",
                    "from", origin, "to", origin, "duration", step.edge_wait, "distance_m", 0.,
                    "congestion_count", step.recent, "route_lane_count", lanes))) goto error;
        }
        if (step.stop_wait > 0.) {
            total += step.stop_wait;
            if (collect && !append(segments, Py_BuildValue(
                    "{s:s,s:O,s:O,s:O,s:d,s:d,s:i,s:i}", "type", "wait_for_node",
                    "from", origin, "to", origin, "blocked_node", destination,
                    "duration", step.stop_wait, "distance_m", 0., "congestion_count", step.recent,
                    "route_lane_count", lanes))) goto error;
        }
        if (collect) {
            PyObject *entry = PyDict_Copy(PyTuple_GET_ITEM(edge, 6));
            if (!entry) goto error;
            if (!put(entry, keys->duration, PyFloat_FromDouble(step.duration)) ||
                (step.factor != 1. && !put(entry, keys->speed_factor, PyFloat_FromDouble(step.factor))) ||
                (step.recent != 0 && !put(entry, keys->congestion_count, PyLong_FromLong(step.recent)))) {
                Py_DECREF(entry);
                goto error;
            }
            if (!append(segments, entry)) goto error;
        }
        total += step.duration;
    }
    return Py_BuildValue("Nd", segments, total);
error:
    Py_DECREF(segments);
    return nullptr;
}

static PyMethodDef methods[] = {
    {"evaluate", evaluate, METH_VARARGS, "Evaluate a prepared corridor against Python reservation tables."},
    {nullptr, nullptr, 0, nullptr},
};
static int visit_keys(PyObject *module, visitproc visit, void *arg) {
    auto *keys = static_cast<SegmentKeys *>(PyModule_GetState(module));
    if (!keys) return 0;
    Py_VISIT(keys->duration);
    Py_VISIT(keys->speed_factor);
    Py_VISIT(keys->congestion_count);
    return 0;
}

static int clear_keys(PyObject *module) {
    auto *keys = static_cast<SegmentKeys *>(PyModule_GetState(module));
    if (!keys) return 0;
    Py_CLEAR(keys->duration);
    Py_CLEAR(keys->speed_factor);
    Py_CLEAR(keys->congestion_count);
    return 0;
}

static void free_keys(void *module) { clear_keys(static_cast<PyObject *>(module)); }

static PyModuleDef definition = {PyModuleDef_HEAD_INIT, "_amr_corridor_native", nullptr,
                                sizeof(SegmentKeys), methods, nullptr, visit_keys,
                                clear_keys, free_keys};

PyMODINIT_FUNC PyInit__amr_corridor_native() {
    auto *module = PyModule_Create(&definition);
    if (!module) return nullptr;
    auto *keys = static_cast<SegmentKeys *>(PyModule_GetState(module));
    keys->duration = PyUnicode_InternFromString("duration");
    keys->speed_factor = PyUnicode_InternFromString("speed_factor");
    keys->congestion_count = PyUnicode_InternFromString("congestion_count");
    if (!keys->duration || !keys->speed_factor || !keys->congestion_count) {
        Py_DECREF(module);
        return nullptr;
    }
    return module;
}
