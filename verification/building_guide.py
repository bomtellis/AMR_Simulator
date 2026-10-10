"""Rebuild the illustrated guide from course actions and verified application images."""
from pathlib import Path
import json
import shutil
import sys
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'visualiser'))

def build(evidence=None, output=None):
    evidence=Path(evidence) if evidence else ROOT/'verification/latest/building-tutorial'
    from amr_tutorial import LESSONS,EXTRA_LESSONS
    from tutorial_bubble import ACTIONS
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Image,PageBreak,Table,TableStyle
    source=ROOT/'docs/building-tutorial'
    out=Path(output) if output else source
    images=out/'images';images.mkdir(parents=True,exist_ok=True)
    if out.resolve()!=source.resolve():
        shutil.copytree(source/'images',images,dirs_exist_ok=True)
    sources={'bubble.png':'visual-100/bubble-Light-1024.png','interpretation.png':'visual-100/planner-Light-1024-tab0.png',
             'proposals.png':'visual-100/planner-Light-1024-tab1.png','workbench.png':'visual-100/workbench.png',
             'floor-settings.png':'visual-100/floor-settings-Light-1024.png',
             'route-preview.png':'visual-100/route-preview-Light-1024.png',
             'route-repair.png':'visual-100/route-repair-Light-1024.png',
             'facility-preview.png':'visual-100/facility-preview-Light-1024.png',
             'location-name.png':'visual-100/location-name-Light-1024.png'}
    for name,source in sources.items():
        if (evidence/source).exists():shutil.copyfile(evidence/source,images/name)
        elif not (images/name).exists():raise FileNotFoundError(evidence/source)
    styles=getSampleStyleSheet();styles['BodyText'].leading=15;styles['BodyText'].allowWidows=0;story=[];md=[]
    styles.add(ParagraphStyle('ActionBullet',parent=styles['BodyText'],leftIndent=14,bulletIndent=2))
    styles.add(ParagraphStyle('ActionLead',parent=styles['BodyText'],keepWithNext=True))
    def p(text,style='BodyText'):
        text=text.replace('\u2192',' > ').replace('\u2013','-').replace('\u2014','-')
        lines=text.split('\n')
        for index,line in enumerate(lines):
            if not line:
                space=Spacer(1,5);space.keepWithNext=True;story.append(space);continue
            bullet=line.startswith('• ')
            paragraph_style='ActionBullet' if bullet else 'ActionLead' if len(lines)>1 and index<len(lines)-1 else style
            story.append(Paragraph(escape(line[2:] if bullet else line),styles[paragraph_style],bulletText='•' if bullet else None))
            space=Spacer(1,3 if '\n' in text else 8)
            space.keepWithNext=paragraph_style=='ActionLead';story.append(space)
        md.append(text.replace('• ','- ')+'\n')
    def picture(name,width=490):
        from PIL import Image as PILImage
        with PILImage.open(images/name) as im:w,h=im.size
        story.append(Image(str(images/name),width=width,height=width*h/w));story.append(Spacer(1,10));md.append(f'![Application screen](images/{name})\n')
    def table(rows,widths):
        t=Table([[Paragraph(escape(str(c)),styles['BodyText']) for c in row] for row in rows],colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#deecf8')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.grey),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story.append(t)
        md.append('\n'.join('| '+' | '.join(str(c) for c in row)+' |' for row in rows)+'\n')
    p('Building flow tutorial','Title')
    p('Create, test and improve a three-floor building in Simple mode. Every floor is 40 x 20 m (800 square metres), with a 3.5 m floor height. The two original lifts sit at x=34 and x=38 m, favouring the far end of the plan.')
    p('Start from Help > Building flow tutorial. A small bubble highlights the actual control and checks project or frozen run state automatically as you work. Next becomes available after all requested actions pass; use it when ready to continue. The last action also checks the whole chapter. Details shows the full instructions and corrections. Back revisits an earlier action. Show control takes you to its workspace without editing inputs or opening Properties. Pause removes the aids; Help > Building flow tutorial resumes them. Help > Restart tutorial bubble rebuilds the bubble at the current step without resetting your edits or progress.')
    p('The bubble avoids the highlighted target, side panes and visible controls. Drag its six-dot grip to move it; a safe position stays put during the current action. More > Reset bubble position returns to automatic placement. New actions and opened editors are placed afresh. With enlarged text, long guidance remains available under More > Show explanation / corrections.')
    p('Long actions use grouped checklists in a scrollable bubble. Inside a dialog, the bubble guides the current control and a blue prompt beside the highlighted field gives its required value. The prompt moves to the next incorrect field as you enter each value; it never edits or saves inputs. Hidden fields first highlight their tab. Required values in the main workspace stay in the bubble. Save each editor when its values match.')
    p('The bubble is an independent nonmodal instruction dialog owned by the main application. Naming, Save and configuration dialogs cannot destroy it. Its name, floor and coordinate guidance remains visible while you edit; finish or cancel that editor before continuing. Closing or pressing Escape on the bubble does not pause it; use Pause explicitly.')
    p('More opens explanations, checkpoints, object rebinding, policy selection, optional lessons and this guide. The larger course window is an optional reference. A checkpoint creates a saved working copy; choose a destination outside the installed example folder. Tutorial progress saves automatically beside that project in .amrproj.tutorial.json as you practise, change chapters and advance actions. Saving the first project or using Save as preserves that progress. Resume restores your position and skips verified chapters and actions to the first unfinished step.')
    picture('bubble.png');story.append(PageBreak())
    p('Example files and setup','Heading1')
    p('Use floor-0.dxf, floor-1.dxf and floor-2.dxf for per-floor import; all use metre units and the same origin. building-three-floors.dxf is a side-by-side presentation for sharing, not the per-floor import source. starter.amrproj contains drawings only. chapter-3/4/5/6/7 checkpoints retain progressively more configuration. reference-dedicated.amrproj and reference-shared.amrproj contain the completed designs.')
    table([['Item','Teaching configuration'],['Circulation','Clean lane y=7; dirty lane y=13. Nodes x=3,8,10,12,18,24,30,34,38 on every floor. Shared transition (3,10).'],
      ['Service endpoints','Floor f: clean (8+2f,4), dirty (8+2f,16); door nodes at y=6 and y=14, 1.2 m clear width.'],
      ['Ground floor','Dispatch (3,10), Clean store (3,7), Dirty receiving (3,13), Wash (5,13). Connect these to the corresponding circulation.'],
      ['Charging bays','Four AMR bays, 1.4 x 1.1 x 2 m, chargers enabled. Local offsets dx=-1/+1, dy=-0.8/+0.8; use each combination once.'],
      ['AMRs','Teaching AMR quantity 4; 1 x 0.7 m; speed 1.5 m/s; payload limit 100 kg and 1.2 x 0.9 x 1.5 m. Motor 96 W, battery 0.1 kWh, initial SOC 15%, charge rate 2 kW, threshold 20%.'],
      ['Payloads','Clean tote and Dirty cart: 0.8 x 0.6 x 1 m, 20 kg, lengthways.'],
      ['Lifts','L1=(34,10), L2=(38,10), all floors. Car 2 x 2 x 2.5 m; speed 0.5 floors/s; door 4 s; boarding 3 s; health decay 0. Shaft 2 x 2 m, landing 1 m, clearance 0.1 m.'],
      ['Building operations','Load/unload 5 s; idle return off; opportunity charging off; initial low SOC demonstrates charging. Dirty receiving requires wash at Wash, 60 s; Wash capacity 1.']],[110,380])
    story.append(PageBreak())
    for i,lesson in enumerate(LESSONS):
        p(f'{i+1}. {lesson[1]}','Heading1');p('Purpose and expected result: '+lesson[4])
        for n,(_,action,_) in enumerate(ACTIONS[i],1):p(f'{n}. {action}')
        if i==4:
            p('Enter one highlighted value at a time. The blue field prompt follows the next value that differs from the checklist. Unloaded robot weight may remain Unspecified; it is optional report metadata. Payload Loaded weight must be 20 kg for this tutorial.')
            if (images/'tutorial-next-field.png').exists():picture('tutorial-next-field.png',width=380)
        if i==5:
            p('In Layout choose Routes on the drawing toolbar, or Layout > Routes, to open Route view. Select clean or dirty. Profile colour changes the permitted-edge colour; Blocked colour changes the dotted excluded directions. Show blocked directions and Show profile labels are independent display switches. Arrows distinguish one-way permission. Profile details lists permitted and blocked directions and lift allowances. Colours save as personal preferences and do not change permissions.')
            if (images/'layout-route-views.png').exists():picture('layout-route-views.png',width=490)
            p('Dedicated profiles permit only the matching lane/service nodes and their designated lift stops (L1 for clean, L2 for dirty). Shared profiles retain lane permissions but include both sets of lift stops and both lift IDs. Dispatch and shared transition areas remain available to empty AMR travel under the existing model. Changing the course policy describes your chosen inputs; it does not configure routes for you.')
            p('Layout has Add node / transition, Add edge between nodes and Route profiles. The profile editor offers Select nodes and edges in Layout. Its dedicated toolbar keeps Floor, Nodes / Edges, selection counts, Finish selection and Cancel selection visible while you use the existing drawing.')
            p('Orange rings and dashed links show the permissions required by the selected tutorial policy; blue marks selected permissions. Guidance follows each missing node, then each directed edge, across floors. Overlapping nodes and zero-length access links offer a choice of names. Changing floors retains previous selections. Finish selection returns a draft to the profile editor; Apply Changes and Save All commit it. Cancel selection retains the previous draft.')
            for image,width in [('layout-route-menu.png',240),('route-profile-graphical-control.png',370),('route-policy-layout-selection.png',490)]:
                if (images/image).exists():picture(image,width=width)
        if i==0:picture('floor-settings.png',width=400)
        if i==2:
            p('The canvas shows the finished route as a dashed preview and numbers each click. The highlighted marker is the next click; it moves as actual nodes and links are created. Use the normal Corridor, Door and Location tools. Door openings are applied through Properties, which you open explicitly. Each route stays on its indicated floor; no preview changes the project.')
            p('Next remains unavailable while a required point, link, door opening or service name is missing or incorrect. Finish a completed route with Escape before continuing. Checks run automatically and show corrections on their actual floor and canvas position; an existing corridor with an incorrect width, direction or length is highlighted for a Properties repair. Renamed service locations retain their bound roles; a deleted role needs repair or rebinding. Undoing an earlier connection blocks progress again. Chapter navigation also checks unfinished work.')
            picture('route-preview.png');picture('route-repair.png')
        if i==3:
            p('Four ground-floor markers show Dispatch (3,10), Clean store (3,7), Dirty receiving (3,13) and Wash (5,13). Choose Location, click the orange marker and enter the shown name. Save creates the location and its stated 0.1 m corridor access link, splitting a corridor segment if needed. The next missing facility is highlighted automatically. Cancel leaves the project unchanged. A wrong position or removed access link blocks Next and identifies the repair; Undo/Redo includes the placement and access link together.')
            p('The same contextual coordinate entry and pointer preview are available for Node, Door, Location, Department, Lift and Edge tools. Coordinates are in metres and use the active floor. Object/grid snapping is shown before insertion; typed X,Y bypasses grid and opens the normal editor. Boundary and rectangle tools retain their existing entries and also show pointer coordinates. Facility, department and lift steps show spatial hints; every other stage highlights its actual control and validates completion automatically.')
            picture('facility-preview.png');picture('location-name.png')
            p('Washing uses the visible location Properties fields. At Dirty receiving set Wash cycle required to Yes, Wash location to Wash, and Wash duration (s) to 60. The bubble highlights each field, then Apply changes. At Wash enter 1 in Service capacity (AMRs) and Apply changes; this is the simulator limit for simultaneous service, including washing. Draft values do not complete these actions until applied.')
            if (images/'washing-properties.png').exists():picture('washing-properties.png',width=300)
        p('Check: '+lesson[4]+' If it fails, the bubble names the first correction; More > Show explanation / corrections lists the remaining findings.')
        if i==4:
            p('The department Floor control is editable in Details. Lift and floors contains an editable stop table: enter X/Y for each served floor. When a requested field is on another tab, the bubble highlights that tab first; it then highlights the field and its required value. Save the nested editor, then the list; the lift list instead applies each saved lift and closes with Close.')
            for image in ('department-floor.png','lift-stop-positions.png'):
                if (images/image).exists():picture(image,width=350)
        if i==6:p('Stores scopes: D0,D1,D2 with Clean store pickup and Clean-Ff drop-off. Linen scopes: Dirty-Ff pickup and Dirty receiving drop-off. Each department operates 06:00-08:00. Four Monday release times create 24 outbound tasks; clean returns add 12 tasks. Use 5 January 2026, 06:00-08:00, Simple. Completed normal reference runs have 36 completed, 0 failed and 0 pending, with both lifts, charging and 12 AMR wash cycles.')
        if i==6:
            p('Category labels retain Stores and Linen even if the saved flow names are Clean and Dirty. Basics has Service target (s): enter 600 for each department or configured group. Returns & stock has Return route profile: choose clean for Stores. Department actions > Configure multiple exposes these same values for shared group settings. Schedule & staff > Edit times uses Add time for each HH:MM value, then OK. The tutorial validates effective saved department/group settings, rather than requiring hidden category defaults.')
            p('For Linen, Locations & routing must use department locations as pickup/source before Drop-off destinations > Select is enabled. The bubble highlights that prerequisite first, then Select, Dirty receiving and OK. For Stores use department locations as drop-off and choose Clean store as pickup.')
            p('In the Check pane, Demand preview sits beside Run checks. Click it, then Build preview; the bubble follows both buttons. Review Tasks, Timetable and Rules and reconciliation for D0, D1 and D2 and both clean and dirty routes. Planned deliveries and collections appear in the preview; the clean returns are runtime-dependent work created during simulation.')
            p('Run checks also evaluates Task routes: every explicit task and each possible pickup/drop-off pair in active resolved demand rules, including return routes. It honours profile node, directed-edge and lift permissions and manual task extensions. Blocked results identify the affected task or rule, department, profile and leg. Counts describe route definitions, including conditional work; they do not predict release totals. Edit permissions or geometry in Layout, then rerun checks. Clearance, capacity, outages and timing require simulation.')
            if (images/'task-route-checks.png').exists():picture('task-route-checks.png',width=490)
            for image in ('linen-enabled-destination.png','check-demand-preview.png'):
                if (images/image).exists():picture(image,width=490)
            for image in ('demand-service-target.png','demand-return-profile.png'):
                if (images/image).exists():picture(image,width=400)
        if i==8:
            p('Review > Route checks reruns task navigation against the saved run input snapshot, independently of current project edits. The table shows reachable, blocked or invalid routes and their source settings. Unverified logs without an input snapshot have no route coverage; current project inputs are never substituted. These are static permission checks, not proof that recorded movements physically completed.')
            if (images/'review-route-checks.png').exists():picture('review-route-checks.png',width=490)
            p('Washing services the AMR after a designated delivery. Payload decontamination and contamination during every empty movement are not simulated. Use the linked payload transition evidence to follow loaded transport; do not infer contamination state from it.')
        if i==9:picture('interpretation.png')
        if i==10:picture('proposals.png')
        story.append(PageBreak())
    p('Comparisons, evidence and portability','Heading1')
    p('Review and confirm a closed building boundary, circulation, wall openings, retained facilities and prohibited areas on every floor. Ambiguous/open boundaries or absent circulation need repair; the drawing bounding box is never treated as the building boundary. Metre and millimetre drawings, transformed blocks and supported curves are flattened with maximum 10 mm deviation. Layer roles and registered offsets/rotation are saved in the study.')
    p('A 1 m grid screens aligned shaft/landing footprints; 0.25 m paths connect permitted circulation. The eight-site shortlist uses demand-weighted directed graph distances. Five non-overlapping two-lift proposals retain equipment, identities, demand and flow permissions. Structural feasibility requires user review. Inspect every proposed connector and floor before applying a layout.')
    p('The suite includes normal, twice-volume peak, L1 outage, L2 outage, one lift at half speed, a 15-minute important-corridor closure, reduced charging and slow washing. Outage/slow events run from 5 to 20 minutes after the start. Charging and washing are separate variants. Each layout replays the same recorded baseline arrivals, including return requests captured from the initial reference run. Returns are then independent frozen requests; layouts do not regenerate return arrival times. Requests without a service target receive the study 10-minute target.')
    p('Only complete, reconciled and comparable results can rank. Protect every department floor/flow on-time rate and completed volume relative to current layout, then rank by worst floor/flow service, horizontal distance and lift wait. Horizontal loaded/empty movement is distinct from vertical lift travel. Outage reachability is topological access during the event; task evidence shows waiting and subsequent service. Dedicated permissions can prohibit backup access; relocation alone cannot remove that constraint or add capacity.')
    p('Create design variant saves a separate .amrproj by default. Apply selected layout is an explicit undoable change and invalidates current checks, while historical run evidence stays frozen. Changed project inputs, drawing bytes or software mark a study stale. Stop evaluation retains finished runs; reevaluate resumes verified finished runs and retries incomplete work. Locate moved run accepts matching registered evidence only.')
    p('Retain the project, its .tutorial.json and .lift-study.json companions, and the referenced study/run folders together. Project drawings are embedded portably. Companion records contain registered paths; use moved-run relinking after moving run folders. PDF/CSV comparison exports are convenient summaries; the study records and immutable run evidence explain them.')
    path=evidence/'integration-final/smoke.json'
    if path.exists():
        data=json.loads(path.read_text());p('Verified example improvement','Heading2')
        for policy,result in data['policies'].items():
            r=result['recommendation'];p(f"{policy.title()}: {r['id']}; worst floor/flow on-time {r['worst_service']:.1%}; suite horizontal change {r['distance_change_m']:.1f} m; lift-wait change {r['wait_change_sec']:.1f} s. Every floor/flow passed its baseline service guard. These are deterministic example results, not a claim for another drawing or policy.")
    story.append(PageBreak());p('Additional lessons','Heading1')
    for title,action,stage in EXTRA_LESSONS:p(title+' ('+stage+')','Heading2');p(action)
    p('Use More > Complete interface reference for the full inventory of workspaces, commands, dialogs and labelled controls. It maps each to a main lesson, optional lesson or contextual reference, including compatibility windows. Detailed development and LTN tests/workloads are excluded from this increment.')
    def footer(canvas,doc):
        canvas.setFont('Helvetica',8);canvas.drawString(45,20,'AMR Simulator | Building flow tutorial | Simple mode');canvas.drawRightString(550,20,str(doc.page))
    SimpleDocTemplate(str(out/'Building-Flow-Tutorial.pdf'),pagesize=A4,leftMargin=45,rightMargin=45,topMargin=40,bottomMargin=40).build(story,onFirstPage=footer,onLaterPages=footer)
    (out/'Building-Flow-Tutorial.md').write_text('\n'.join(md),encoding='utf-8')

if __name__=='__main__':build()
