#pragma once

struct TimingStep {
    double edge_wait, stop_wait, duration, factor, finish;
    int recent;
};

inline double larger(double a, double b) { return a < b ? b : a; }
inline double smaller(double a, double b) { return b < a ? b : a; }

template <class Rows>
inline int scan_start(Rows rows, double at, double spacing, double max_duration) {
    double threshold = at - larger(0., spacing) - larger(0., max_duration);
    int lo = 0, hi = rows.size();
    while (lo < hi) {
        int mid = lo + (hi - lo) / 2;
        if (rows.start(mid) < threshold) lo = mid + 1; else hi = mid;
    }
    return lo;
}

template <class Rows>
inline double directed_start(Rows rows, double at, double duration, double spacing,
                                 double max_duration) {
    for (;;) {
        double adjusted = at;
        for (int i = scan_start(rows, at, spacing, max_duration); i < rows.size(); ++i) {
            double start = rows.start(i), end = rows.end(i);
            if (start > at + duration + spacing) break;
            if (at >= start - 1e-9) {
                adjusted = larger(adjusted, start + spacing);
                adjusted = larger(adjusted, (end + spacing) - duration);
            } else if (at + duration > end - spacing) {
                adjusted = larger(adjusted, end + spacing);
            }
        }
        if (adjusted <= at + 1e-9) return at;
        at = adjusted;
    }
}

template <class Rows>
inline double edge_start(Rows physical, Rows directed, double at, double duration,
                             double spacing, int capacity, double physical_max, double directed_max) {
    for (;;) {
        int overlap = 0;
        double next = 0.;
        for (int i = scan_start(physical, at, spacing, physical_max); i < physical.size(); ++i) {
            double start = physical.start(i), end = physical.end(i);
            if (start > at + duration + spacing) break;
            double protected_start = start - spacing, protected_end = end + spacing;
            if (!(at + duration <= protected_start || at >= protected_end)) {
                if (!overlap || protected_end < next) next = protected_end;
                ++overlap;
            }
        }
        double candidate = overlap >= capacity ? larger(at, next) : at;
        candidate = larger(candidate, directed_start(directed, candidate, duration, spacing, directed_max));
        if (candidate <= at + 1e-9 && overlap < capacity) return at;
        at = candidate;
    }
}

template <class Rows>
inline double node_arrival(Rows nodes, double at, double spacing, double max_duration) {
    for (;;) {
        bool blocked = false;
        double next = 0.;
        for (int i = scan_start(nodes, at, spacing, max_duration); i < nodes.size(); ++i) {
            double start = nodes.start(i), end = nodes.end(i);
            if (start > at + spacing) break;
            double protected_start = start - spacing, protected_end = end + spacing;
            if (protected_start <= at && at < protected_end) {
                if (!blocked || protected_end < next) next = protected_end;
                blocked = true;
            }
        }
        if (!blocked) return at;
        at = next;
    }
}

template <class Rows>
inline TimingStep time_edge(Rows physical, Rows directed, Rows nodes,
                                double physical_max, double directed_max, double node_max,
                                double at, double base, double spacing, int capacity,
                                double window, double slowdown, double min_factor) {
    int recent = 0;
    for (int i = scan_start(physical, at - window, 0., physical_max); i < physical.size(); ++i) {
        if (physical.start(i) > at + window) break;
        if (physical.end(i) >= at - window) ++recent;
    }
    const double congestion = larger(min_factor, 1. - recent * slowdown);
    double factor = larger(.01, smaller(congestion, 1.));
    const double travel = base / factor;
    const double start = (physical.size() || directed.size())
        ? edge_start(physical, directed, at, travel, larger(0., spacing),
                     capacity, physical_max, directed_max)
        : at;
    const double edge_wait = larger(0., start - at);
    double depart = edge_wait > 0. ? start : at;
    const double proposed = depart + travel;
    const double safe = nodes.size() ? node_arrival(nodes, proposed, spacing, node_max) : proposed;
    const double node_wait = larger(0., safe - proposed);
    double stop_wait = 0., duration = travel;
    if (node_wait > 0.) {
        const double adjusted = travel + node_wait;
        const double effective = base / larger(adjusted, 1e-9);
        const double minimum = larger(.01, smaller(min_factor, 1.));
        if (effective >= minimum) {
            duration = adjusted;
            factor = smaller(factor, effective);
        } else {
            duration = base / minimum;
            stop_wait = larger(0., safe - (depart + duration));
            factor = minimum;
        }
    }
    if (stop_wait > 0.) depart += stop_wait;
    return {edge_wait, stop_wait, duration, factor, depart + duration, recent};
}
