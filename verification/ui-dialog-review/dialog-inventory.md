# Dialog structural assessment

Each direct `QDialog` subclass in `visualiser` is listed. This is source inspection,
not a visual claim for every possible data-dependent state. The revision images
and measured runtime captures in this directory supplement the inventory.

| Dialog | Priority | Layout observations |
| --- | --- | --- |
| [MultiSelectPicker](../../visualiser/advanced_dialogs.py#L99) | low | No static crowding flag; local scroll |
| [RouteProfilesEditorV2](../../visualiser/advanced_dialogs.py#L284) | high | dense horizontal layout, long explanatory copy, no local scroll |
| [TaskFormDialog](../../visualiser/advanced_dialogs.py#L558) | medium | long explanatory copy, no local scroll |
| [BulkOneToManyTaskDialog](../../visualiser/advanced_dialogs.py#L707) | low | No static crowding flag |
| [MultiDaySelectDialog](../../visualiser/advanced_dialogs.py#L820) | low | No static crowding flag |
| [EditMultipleTasksDialog](../../visualiser/advanced_dialogs.py#L1587) | medium | dense horizontal layout, no local scroll |
| [TaskJumpDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L1430) | medium | theme only on show |
| [TasksByLocationDepartmentDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L1653) | medium | theme only on show |
| [LocationInventoryPayloadDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L1882) | medium | theme only on show |
| [LocationInventorySpacesDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L1956) | medium | theme only on show |
| [PayloadSpaceMaximumUtilisationDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L2019) | high | long explanatory copy, no local scroll, theme only on show |
| [AmrPayloadMonitorDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L2093) | medium | theme only on show |
| [LiftMonitorDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L2177) | medium | theme only on show |
| [FailedTasksDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L2772) | medium | theme only on show |
| [LocationInventoryPayloadDialog](../../visualiser/amr_sim_visualiser_pyside6.py#L2883) | medium | theme only on show |
| [DXFLoadingDialog](../../visualiser/app.py#L177) | medium | minimum size, no local scroll |
| [ScheduledTimesDialog](../../visualiser/dialogs.py#L383) | low | No static crowding flag |
| [StaffWeeklyHoursDialog](../../visualiser/dialogs.py#L534) | medium | long explanatory copy, no local scroll |
| [GlobalStaffConfigDialog](../../visualiser/dialogs.py#L628) | medium | long explanatory copy, no local scroll |
| [BulkDepartmentTaskGenerationDialog](../../visualiser/dialogs.py#L899) | high | fixed-width control, dense horizontal layout, long explanatory copy, no local scroll |
| [ConfiguredGroupSelectDialog](../../visualiser/dialogs.py#L1991) | low | No static crowding flag |
| [TaskGenerationSettingsDialog](../../visualiser/dialogs.py#L2029) | high | fixed-width control, dense horizontal layout, long explanatory copy; local scroll |
| [PointEditorDialog](../../visualiser/dialogs.py#L4550) | medium | minimum size, no local scroll |
| [EdgeConnectionsDialog](../../visualiser/dialogs.py#L4733) | low | No static crowding flag |
| [LiftEditorDialog](../../visualiser/dialogs.py#L4834) | medium | minimum size, no local scroll; tabs |
| [LiftListDialog](../../visualiser/dialogs.py#L5181) | low | No static crowding flag |
| [AMRPayloadSlotDialog](../../visualiser/dialogs.py#L5398) | medium | minimum size, no local scroll |
| [AMREditorDialog](../../visualiser/dialogs.py#L5497) | medium | minimum size; tabs; local scroll |
| [PayloadTrackedItemDialog](../../visualiser/dialogs.py#L5834) | medium | minimum size, no local scroll |
| [PayloadEditorDialog](../../visualiser/dialogs.py#L5980) | medium | minimum size, no local scroll; tabs |
| [PayloadListDialog](../../visualiser/dialogs.py#L6280) | low | No static crowding flag |
| [AMRListDialog](../../visualiser/dialogs.py#L6440) | low | No static crowding flag |
| [RouteProfilesEditor](../../visualiser/dialogs.py#L6686) | low | No static crowding flag |
| [PeopleMovementEditorDialog](../../visualiser/dialogs.py#L6700) | high | minimum size, long explanatory copy, no local scroll; tabs |
| [PeopleMovementListDialog](../../visualiser/dialogs.py#L7194) | medium | minimum size, no local scroll |
| [ScenarioEventDialog](../../visualiser/dialogs.py#L7421) | medium | minimum size, no local scroll; tabs |
| [ScenarioTestingDialog](../../visualiser/dialogs.py#L7706) | medium | minimum size, no local scroll |
| [CorridorSettingsDialog](../../visualiser/dialogs.py#L8149) | medium | minimum size, no local scroll; tabs |
| [SimulationSettingsDialog](../../visualiser/dialogs.py#L8639) | medium | minimum size, long explanatory copy; tabs; local scroll |
| [WasteStreamEditorDialog](../../visualiser/dialogs.py#L9065) | low | No static crowding flag |
| [WasteStreamListDialog](../../visualiser/dialogs.py#L9135) | low | No static crowding flag |
| [MassCollectionEditorDialog](../../visualiser/dialogs.py#L9244) | high | fixed-width control, dense horizontal layout, long explanatory copy, no local scroll |
| [MassCollectionListDialog](../../visualiser/dialogs.py#L9468) | low | No static crowding flag |
| [DepartmentWasteStreamSettingsDialog](../../visualiser/dialogs.py#L9590) | low | No static crowding flag |
| [DepartmentWasteStreamItemDialog](../../visualiser/dialogs.py#L9733) | medium | long explanatory copy, no local scroll |
| [DepartmentDropoffZoneCreationDialog](../../visualiser/dialogs.py#L9998) | low | No static crowding flag; local scroll |
| [DepartmentEditorDialog](../../visualiser/dialogs.py#L10159) | high | fixed-width control, dense horizontal layout, long explanatory copy, no local scroll |
| [BulkDepartmentWasteStreamControlDialog](../../visualiser/dialogs.py#L10899) | medium | long explanatory copy, no local scroll |
| [TaskCategoryCommonLocationWizard](../../visualiser/dialogs.py#L11429) | high | dense horizontal layout, long explanatory copy, no local scroll |
| [TaskCategorySharedBinGroupWizard](../../visualiser/dialogs.py#L11748) | high | fixed-width control, dense horizontal layout, long explanatory copy, no local scroll |
| [DepartmentListDialog](../../visualiser/dialogs.py#L12221) | low | No static crowding flag |
| [ArrayInventorySpacesDialog](../../visualiser/dialogs.py#L13284) | low | No static crowding flag |
| [InventorySpacesDialog](../../visualiser/dialogs.py#L13404) | medium | dense horizontal layout, no local scroll |
| [LocationSpacesManagerDialog](../../visualiser/inventory_spaces_manager.py#L87) | high | minimum size, dense horizontal layout, long explanatory copy, no local scroll |
| [PdfUnderlayDialog](../../visualiser/pdf_underlay.py#L158) | high | minimum size, no local scroll, theme only on show |
| [RunChecksDialog](../../visualiser/project_checks_panel.py#L270) | medium | theme only on show |
| [QuickStartDialog](../../visualiser/quick_start.py#L95) | medium | theme only on show; tabs |

Total: 57 dialogs; 11 high, 29 medium, 17 low.
