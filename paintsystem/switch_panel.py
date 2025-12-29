import bpy
from bpy.types import PropertyGroup
from bpy.props import BoolProperty, CollectionProperty, IntProperty, StringProperty
from bpy.utils import register_classes_factory
from bpy.types import Operator

from ..custom_icons import get_icon

class SwitchPanelItem(PropertyGroup):
    """Switch panel data"""
    name: StringProperty(
        name="Name",
        description="Name of the switch panel item",
        default="",
    )
    icon: StringProperty(
        name="Icon",
        description="Icon of the switch panel item",
        default="",
    )
    custom_icon: StringProperty(
        name="Custom Icon",
        description="Custom icon of the switch panel item",
        default="",
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Enabled",
        default=False,
    )

class PAINTSYSTEM_OT_SetActiveSwitchPanel(Operator):
    """Set the active switch panel"""
    bl_idname = "paint_system.set_active_switch_panel"
    bl_label = "Set Active Switch Panel"
    bl_options = {'INTERNAL'}
    bl_description = "Set the active switch panel"
    
    switch_panel_name: StringProperty(name="Switch Panel Name")
    
    def execute(self, context):
        switch_panel_manager = SwitchPanelManager(context.scene.ps_scene_data, 'paint_switch_panels', context.scene.ps_scene_data, 'paint_switch_panels_active_index')
        panel = switch_panel_manager.get_switch_panel_by_name(self.switch_panel_name)
        if not panel:
            return {'CANCELLED'}
        if panel.enabled:
            panel.enabled = False
        else:
            switch_panel_manager.set_active_switch_panel(self.switch_panel_name)
        return {'FINISHED'}

class SwitchPanelManager():
    """Switch panel manager"""
    
    def __init__(self, data_ptr, propname: str, active_dataptr, active_propname: str, force_active: bool = False):
        """Initialize the SwitchPanelManager
        Args:
            data_ptr (PropertyGroup): The data block instance holding the collection property (e.g., scene, object, material).
            propname (str): The string name of the collection property.
            active_dataptr (PropertyGroup): The data block instance holding the active index property.
            active_propname (str): The string name of the integer property for the active index.
            force_active (bool, optional): If True, forces at least one switch panel to be active. Defaults to False.
        """
        self.data_ptr = data_ptr
        self.propname = propname
        self.active_dataptr = active_dataptr
        self.active_propname = active_propname
        self.force_active = force_active

    @property
    def collection(self):
        """Dynamically gets the collection from the data block."""
        return getattr(self.data_ptr, self.propname)

    @property
    def active_index(self):
        """Dynamically gets the active index from its data block."""
        return getattr(self.active_dataptr, self.active_propname)
    
    def get_active_switch_panel(self):
        for switch_panel in self.collection:
            if switch_panel.enabled:
                return switch_panel
        return None
    
    def add_switch_panel(self, name: str, icon: str = None, custom_icon: str = None):
        new_switch_panel = self.collection.add()
        new_switch_panel.name = name
        if icon:
            new_switch_panel.icon = icon
        if custom_icon:
            new_switch_panel.custom_icon = custom_icon
        if len(self.collection) == 1 and self.force_active:
            new_switch_panel.enabled = True
        return new_switch_panel
    
    def get_switch_panel_by_name(self, name: str):
        for switch_panel in self.collection:
            if switch_panel.name == name:
                return switch_panel
        return None
    
    def set_active_switch_panel(self, name: str):
        for switch_panel in self.collection:
            if switch_panel.name == name:
                switch_panel.enabled = True
            else:
                switch_panel.enabled = False
    
    def switch_panel_ui(self, layout: bpy.types.UILayout, context: bpy.types.Context):
        if len(self.collection) == 0:
            return
        row = layout.row()
        row.alignment = 'LEFT'
        for switch_panel in self.collection:
            btn_row = row.row(align=True)
            btn_row.alignment = 'LEFT'
            op_params = {
                "operator": "paint_system.set_active_switch_panel",
                "text": switch_panel.name,
                "emboss": switch_panel.enabled,
                "depress": switch_panel.enabled,
            }
            if switch_panel.icon:
                op_params["icon"] = switch_panel.icon
            if switch_panel.custom_icon:
                op_params["icon_value"] = get_icon(switch_panel.custom_icon)
            btn_row.operator(**op_params).switch_panel_name = switch_panel.name
            if switch_panel.enabled:
                btn_row.operator("paint_system.set_active_switch_panel", text="", icon="X").switch_panel_name = switch_panel.name
        return row

classes = (
    SwitchPanelItem,
    PAINTSYSTEM_OT_SetActiveSwitchPanel,
)

register, unregister = register_classes_factory(classes)