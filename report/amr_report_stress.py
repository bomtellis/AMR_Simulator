"""PDF content for verified, explicitly selected stress-test comparisons."""
from xml.sax.saxutils import escape
from collections import defaultdict
from itertools import combinations

import pandas as pd
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, CondPageBreak, PageBreak


def affected_assets(record):
    if 'amr_speed_percent' in record:
        return f"All AMRs at {record['amr_speed_percent']}% speed"
    return ' + '.join(sorted({asset for event in record['events'] for asset in event['resource_ids']})) or record['name']


def impact_key(record):
    """Unfulfilled work takes precedence over delays of completed work."""
    m = record['metrics']
    return (not m['passed'], m['unmet_count'], m['failed'], m['pending'],
            m['added_delay_sec'], m['latest_completion_sec'])


def impact_summary(study):
    trials = study['trials']
    failures = sorted((r for r in trials if not r['metrics']['passed']), key=impact_key, reverse=True)
    passing = [r for r in trials if r['metrics']['passed']]
    delays = sorted(passing, key=lambda r: r['metrics']['added_delay_sec'], reverse=True)
    # Only compare full lift outages with exactly the same simultaneous window.
    # Slowdowns, mixed resource types and staggered outages remain in the general ranking.
    groups = defaultdict(list)
    for record in trials:
        events = record['events']
        windows = {(e.get('start_datetime', e.get('start_time', '')),
                    e.get('end_datetime', e.get('end_time', ''))) for e in events}
        if (events and len(windows) == 1 and all(e['resource_type'] == 'lift'
                and (e['availability_percent'] == 0 or e['speed_factor'] == 0) for e in events)):
            window = next(iter(windows))
            if all(window):
                groups[window].append(record)
    cohorts = []
    for window, records in sorted(groups.items()):
        by_assets = defaultdict(list)
        for record in records:
            assets = tuple(sorted({a for e in record['events'] for a in e['resource_ids']}))
            by_assets[assets].append(record)
        lifts = sorted({a for assets in by_assets for a in assets})
        # Repeated selections for an identical outage are represented conservatively.
        cells = {assets: max(items, key=impact_key) for assets, items in by_assets.items()}
        singles = [cells[(lift,)] for lift in lifts if (lift,) in cells]
        pairs = [cells[assets] for assets in combinations(lifts, 2) if assets in cells]
        criticality = []
        for lift in lifts:
            related = [r for r in pairs if lift in {a for e in r['events'] for a in e['resource_ids']}]
            passed_pairs = [r for r in related if r['metrics']['passed']]
            criticality.append(dict(lift=lift, single=cells.get((lift,)), pairs=len(related),
                failing_pairs=sum(not r['metrics']['passed'] for r in related),
                mean_pair_delay_sec=(sum(r['metrics']['added_delay_sec'] for r in passed_pairs) / len(passed_pairs)
                                     if passed_pairs else None),
                passing_pairs=len(passed_pairs)))
        criticality.sort(key=lambda row: (row['single'] is not None,
                         impact_key(row['single']) if row['single'] else ()), reverse=True)
        cohorts.append(dict(window=window, lifts=lifts, cells=cells, singles=singles, pairs=pairs,
            criticality=criticality, repeated=sum(len(v) - 1 for v in by_assets.values()),
            complete_singles_pairs=(len(singles) == len(lifts) and len(pairs) == len(lifts)*(len(lifts)-1)//2)))
    return dict(failures=failures, delays=delays, cohorts=cohorts)


def append_impact_summary(story, study, styles):
    from amr_report_pdf_report import table_from_df
    from amr_report_analysis import fmt_duration

    summary = impact_summary(study)
    trials = study['trials']
    if 'speed_sweep' in study:
        from amr_scenario_study import speed_sweep_description
        story.append(Paragraph('All-AMR speed sweep summary', styles['Heading2']))
        story.append(Paragraph(escape(speed_sweep_description(study['speed_sweep'])), styles['BodyText']))
        story.append(Paragraph('100% is normal operation. Each lower level applies to every AMR, including all quantity '
            'instances, for the entire run and any work completing after demand ends. Levels decrease by 5 percentage '
            'points, down to 5%. Results below cover only the selected trials. Travel speeds are percentages of each '
            'AMR configuration; lift speeds and handling times retain their configured values.', styles['BodyText']))
        rows = []
        for record in [study['baseline'], *sorted(trials, key=lambda r: -r['amr_speed_percent'])]:
            m = record['metrics']
            rows.append([f"{record['amr_speed_percent']}%", 'Pass' if m['passed'] else 'Does not pass',
                         m['unmet_count'], m['failed'], m['pending'], f"{m['added_delay_sec']/3600:,.2f}",
                         fmt_duration(m['latest_completion_sec'])])
        story.append(table_from_df(pd.DataFrame(rows, columns=['Fleet speed', 'Outcome', 'Unmet', 'Failed', 'Pending',
            'Added delay (h)', 'Latest finish']), [27*mm, 38*mm, 26*mm, 26*mm, 26*mm, 50*mm, 54*mm],
            styles, format_values=False))
        story.append(Paragraph('Added delay is cumulative across completed service obligations. It excludes unfinished '
            'work, so assess service failures separately. Latest finish is elapsed simulation time. '
            'A passing level is not a guarantee of any untested speed or a delivery-time SLA.', styles['Small']))
        story.append(PageBreak())
        return
    if not trials:
        return
    story.append(Paragraph('Worst-case impact summary', styles['Heading2']))
    story.append(Paragraph(f"{len(trials) - len(summary['failures'])} of {len(trials)} selected trials pass; "
        f"{len(summary['failures'])} do not pass. Rankings below apply only to selected trials in this study. "
        'Service failures are assessed separately from delay because unfinished work contributes no completion delay.', styles['BodyText']))

    def ranking(title, records):
        if not records:
            return
        story.append(CondPageBreak(40*mm))
        story.append(Paragraph(title, styles['Heading3']))
        rows = []
        baseline_finish = study['baseline']['metrics']['latest_completion_sec']
        for r in records[:5]:
            m = r['metrics']
            rows.append([affected_assets(r), r['id'][:8], m['unmet_count'], m['failed'], m['pending'],
                         f"{m['added_delay_sec']/3600:,.1f}",
                         f"{(m['latest_completion_sec']-baseline_finish)/60:+.1f}"])
        story.append(table_from_df(pd.DataFrame(rows, columns=['Affected assets', 'Trial ref.', 'Unmet', 'Failed',
            'Pending', 'Added delay (h)', 'Finish change (min)']),
            [65*mm, 27*mm, 22*mm, 22*mm, 22*mm, 43*mm, 46*mm], styles, format_values=False))

    ranking('Largest service failures (up to 5)', summary['failures'])
    ranking('Largest delays among passing trials (up to 5)', summary['delays'])
    latest = max(trials, key=lambda r: r['metrics']['latest_completion_sec'])
    baseline_finish = study['baseline']['metrics']['latest_completion_sec']
    story.append(Paragraph('Added delay is cumulative across service obligations, not extra elapsed run time. '
        f"Normal-operation latest finish: {escape(fmt_duration(baseline_finish))}. "
        f"Latest selected finish: {escape(fmt_duration(latest['metrics']['latest_completion_sec']))} "
        f"({escape(affected_assets(latest))}; change "
        f"{(latest['metrics']['latest_completion_sec'] - baseline_finish)/60:+.1f} minutes). "
        'Unmet obligations and failed tasks can describe the same incident and must not be added together.', styles['Small']))

    for cohort in summary['cohorts']:
        story.append(PageBreak())
        story.append(Paragraph('Lift shutdown criticality', styles['Heading2']))
        lifts, cells = cohort['lifts'], cohort['cells']
        story.append(Paragraph(f"Simultaneous full shutdown: {escape(cohort['window'][0])} to "
            f"{escape(cohort['window'][1])}. Selected coverage: {len(cohort['singles'])} single-lift outages "
            f"and {len(cohort['pairs'])} pairs across {len(lifts)} lifts. "
            + ('Every single and pair of these lifts is represented. ' if cohort['complete_singles_pairs'] else
               'Single/pair coverage is incomplete; unselected or untested cases are not zero impact. ')
            + 'This table does not establish the worst case for three or more simultaneous outages.', styles['BodyText']))
        if cohort['repeated']:
            story.append(Paragraph('Repeated identical outages use the worst recorded outcome in each cell.', styles['Small']))
        passed_singles = [r for r in cohort['singles'] if r['metrics']['passed']]
        passed_pairs = [r for r in cohort['pairs'] if r['metrics']['passed']]
        findings = []
        for label, records in [('Single shutdown with the largest delay', passed_singles),
                               ('Pair shutdown with the largest delay', passed_pairs)]:
            if records:
                worst = max(records, key=lambda r: r['metrics']['added_delay_sec'])
                findings.append(f"{label}: {escape(affected_assets(worst))}, "
                                f"{worst['metrics']['added_delay_sec']/3600:,.1f} cumulative hours.")
        if findings:
            story.append(Paragraph(' '.join(findings) + ' These delay comparisons include passing trials only.', styles['BodyText']))
        rows = []
        for row in cohort['criticality']:
            single = row['single']
            rows.append([row['lift'], ('Pass' if single['metrics']['passed'] else 'Does not pass') if single else 'Not selected',
                f"{single['metrics']['added_delay_sec']/3600:,.1f}" if single else '-',
                str(single['metrics']['unmet_count']) if single else '-',
                f"{row['mean_pair_delay_sec']/3600:,.1f}" if row['mean_pair_delay_sec'] is not None else '-',
                str(row['passing_pairs']), f"{row['failing_pairs']} / {row['pairs']}"])
        story.append(table_from_df(pd.DataFrame(rows, columns=['Lift', 'Single outcome', 'Single delay (h)', 'Single unmet',
            'Mean pair delay (h)', 'Passing pairs', 'Failing / tested pairs']),
            [25*mm, 34*mm, 34*mm, 28*mm, 45*mm, 34*mm, 47*mm], styles, format_values=False))
        story.append(Paragraph('Ordered by single-outage impact, with service failures first. Mean pair delay includes only '
            'passing pairs containing that lift. It describes those combinations, not the isolated contribution of the lift; '
            'partner effects and routing changes are included. Pair means with different coverage are not directly comparable.', styles['Small']))
        # Keep matrix readable on landscape A4. Larger fleets retain the rankings and detail tables.
        if len(lifts) <= 10:
            story.append(CondPageBreak((16 + 7*len(lifts))*mm))
            story.append(Paragraph('Shutdown combinations: cumulative added delay (hours)', styles['Heading3']))
            rows = []
            for i, lift in enumerate(lifts):
                row = [lift]
                for j, other in enumerate(lifts):
                    record = cells.get((lift,) if i == j else tuple(sorted((lift, other))))
                    if record is None:
                        value = 'N/S'
                    else:
                        m = record['metrics']
                        value = f"{m['added_delay_sec']/3600:.1f}" + ('' if m['passed'] else ' FAIL')
                    row.append(value if j >= i else '')
                rows.append(row)
            story.append(table_from_df(pd.DataFrame(rows, columns=['Lift', *lifts]),
                [25*mm] + [222*mm/len(lifts)]*len(lifts), styles, format_values=False))
            story.append(Paragraph('Diagonal: single lift shut down. Upper triangle: both lifts shut down. '
                'FAIL: service criterion not met, regardless of recorded delay. N/S: not selected in this window. '
                'See trial details for unmet obligations and exact event settings.', styles['Small']))
    story.append(PageBreak())


def append_stress_story(story, snapshot, styles):
    from amr_report_pdf_report import table_from_df
    from amr_report_analysis import fmt_duration

    story.section('stress_tests')
    story.append(Paragraph('Selected saved trials are compared with their own normal-operation baseline. '
        'These selections are not a claim that every possible disruption has been tested. '
        'Added delay sums positive completion-time changes for comparable service obligations; unmet work is shown separately. '
        'Finishing after demand ends is informational and does not, by itself, fail a trial.', styles['BodyText']))
    for index, study in enumerate(snapshot['studies']):
        if index:
            story.append(PageBreak())
        story.append(Paragraph(escape(study['name']), styles['Heading2']))
        story.append(Paragraph(
            f"Study status: {escape(study['status'])}. Selected disruption trials: {len(study['trials'])} "
            f"of {study['saved_trials']} saved. Demand starts {escape(study['start_datetime'])}; "
            f"duration {escape(fmt_duration(study['horizon_sec']))}. "
            + ('Design inputs match the main report run.' if study['matches_report_inputs'] else
               'Design inputs differ from the main report run; this study uses its own baseline.'), styles['BodyText']))
        story.append(Spacer(1, 7))
        append_impact_summary(story, study, styles)
        story.append(Paragraph('Selected trial results', styles['Heading2']))
        rows = []
        for record in [study['baseline'], *study['trials']]:
            m = record['metrics']
            rows.append([record['name'], 'Pass' if m['passed'] else 'Does not pass', m['completed'],
                         m['failed'], m['pending'], m['unmet_count'],
                         fmt_duration(m['added_delay_sec']), fmt_duration(m['latest_completion_sec'])])
        story.append(table_from_df(pd.DataFrame(rows, columns=['Trial', 'Outcome', 'Completed', 'Failed', 'Pending',
            'Unmet', 'Added delay', 'Latest finish']), [62*mm, 23*mm, 20*mm, 18*mm, 18*mm, 20*mm, 43*mm, 43*mm],
            styles, format_values=False))
        story.append(Paragraph('Durations are shown as h:mm:ss or m:ss. Latest finish is elapsed simulation time. '
                               'Completed/failed/pending counts are tasks; unmet counts are service obligations.', styles['Small']))
        for record in study['trials']:
            story.append(CondPageBreak(55*mm))
            story.append(Paragraph(escape(record['name']), styles['Heading3']))
            m = record['metrics']
            story.append(Paragraph(f"Run status: {escape(m['status'])}. Tasks finishing after demand ends: {m['late']}. "
                f"Run reference: {escape(m['run_key'])}.", styles['Small']))
            if 'amr_speed_percent' in record:
                story.append(Paragraph('The 00:00 to 00:00 window means all day, every day, including work after demand ends.', styles['Small']))
            events = []
            for event in record['events']:
                events.append([event['resource_type'], ', '.join(event['resource_ids']),
                    event.get('start_datetime', event.get('start_time', '')),
                    event.get('end_datetime', event.get('end_time', '')),
                    f"{event['availability_percent']:g}%", f"{100 * event['speed_factor']:g}%"])
            story.append(table_from_df(pd.DataFrame(events, columns=['Resource', 'Affected assets', 'Starts', 'Ends',
                'Availability', 'Speed']), [22*mm, 81*mm, 52*mm, 52*mm, 20*mm, 20*mm], styles, format_values=False))
            if record['unmet_examples']:
                story.append(Paragraph('Unmet obligation examples (up to 10): ' +
                    escape('; '.join(record['unmet_examples'])), styles['Small']))
            story.append(Spacer(1, 8))
        story.append(Paragraph('Baseline run: ' + escape(study['baseline']['metrics']['run_key']) +
            '. Source study: ' + escape(study['path']), styles['Small']))
