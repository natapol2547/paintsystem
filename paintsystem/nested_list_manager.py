import bpy
from bpy.props import StringProperty, IntProperty, EnumProperty
from bpy.types import (PropertyGroup, Operator)
from bpy.utils import register_classes_factory

class BaseNestedListItem(PropertyGroup):
    """Base class for nested list items. Extend this class to add custom properties."""
    id: IntProperty()
    name: StringProperty()
    parent_id: IntProperty(default=-1)
    order: IntProperty()
    type: EnumProperty(
        items=[
            ('FOLDER', "Folder", "Can contain other items"),
            ('ITEM', "Item", "Cannot contain other items")
        ],
        default='ITEM'
    )


class BaseNestedListManager(PropertyGroup):
    """Base class for nested list manager. Override items property in your subclass."""
    active_index: IntProperty()
    next_id: IntProperty(default=0)

    @property
    def item_type(self):
        """Override this to return your custom item type class"""
        return BaseNestedListItem

    @property
    def collection_name(self):
        """Override this to return the name of the collection property"""
        return "items"

    def get_active_item(self):
        """Get currently active item based on active_index"""
        # active_id = self.get_id_from_flattened_index(self.active_index)
        # if active_id != -1:
        #     return self.get_item_by_id(active_id)
        # return None
        if getattr(self, self.collection_name) is None or self.active_index < 0 or self.active_index >= len(getattr(self, self.collection_name)):
            return None
        return getattr(self, self.collection_name)[self.active_index]

    def adjust_sibling_orders(self, parent_id, insert_order):
        """Increase order of all items at or above the insert_order under the same parent"""
        for item in getattr(self, self.collection_name):
            if item.parent_id == parent_id and item.order >= insert_order:
                item.order += 1

    def get_insertion_data(self, active_item=None):
        """Get parent_id and insert_order for new item based on active item"""
        if active_item is None:
            active_item = self.get_active_item()

        parent_id = -1
        insert_order = 1

        if active_item:
            if active_item.type == 'FOLDER':
                # If selected item is a folder, add inside it
                parent_id = active_item.id
                # Find lowest order in folder or default to 1
                orders = [
                    item.order for item in getattr(self, self.collection_name) if item.parent_id == parent_id]
                insert_order = min(orders) if orders else 1
            else:
                # If selected item is not a folder, add at same level
                parent_id = active_item.parent_id
                insert_order = active_item.order

        return parent_id, insert_order

    def add_item(self, name, item_type='ITEM', parent_id=-1, **kwargs) -> item_type:
        """Add a new item to the list"""
        if item_type == 'ITEM' and parent_id != -1:
            parent = self.get_item_by_id(parent_id)
            if parent and parent.type != 'FOLDER':
                return -1

        new_item = getattr(self, self.collection_name).add()
        new_item.id = self.next_id
        new_item.name = name
        new_item.parent_id = parent_id
        new_item.type = item_type
        new_item.order = self.get_next_order(parent_id)

        for key, value in kwargs.items():
            if hasattr(new_item, key):
                setattr(new_item, key, value)

        self.next_id += 1
        return new_item

    def remove_item_and_children(self, item_id, on_delete=None):
        """Remove an item and all its children"""
        to_remove = []

        def collect_children(parent_id):
            for i, item in enumerate(getattr(self, self.collection_name)):
                if item.parent_id == parent_id:
                    to_remove.append(i)
                    if item.type == 'FOLDER':
                        collect_children(item.id)

        # Collect the item index
        item_index = self.get_collection_index_from_id(item_id)
        if item_index != -1:
            to_remove.append(item_index)
            # If it's a folder, collect all children
            item = self.get_item_by_id(item_id)
            if item and item.type == 'FOLDER':
                collect_children(item_id)

            # Remove items from highest index to lowest
            for index in sorted(to_remove, reverse=True):
                if on_delete:
                    on_delete(getattr(self, self.collection_name)[index])
                getattr(self, self.collection_name).remove(index)

            return True
        return False

    def get_next_order(self, parent_id):
        return max((item.order for item in getattr(self, self.collection_name) if item.parent_id == parent_id), default=-1) + 1

    def get_item_by_id(self, item_id):
        for item in getattr(self, self.collection_name):
            if item.id == item_id:
                return item
        return None

    def get_collection_index_from_id(self, item_id):
        for index, item in enumerate(getattr(self, self.collection_name)):
            if item.id == item_id:
                return index
        return -1

    def get_id_from_flattened_index(self, flattened_index):
        flattened = getattr(self, self.collection_name)
        if 0 <= flattened_index < len(flattened):
            return flattened[flattened_index].id
        return -1

    def flatten_hierarchy(self):
        # children = getattr(self, self.collection_name)
        # print("Children:", [(i.id, i.parent_id, i.order) for i in children])
        # flattened = sorted(
        #     children, key=lambda i: (i.order, i.parent_id))
        # return [(item, self.get_item_level_from_id(item.id)) for item in flattened]
        def collect_items(parent_id, level):
            collected = []
            children = sorted(
                [item for item in getattr(self, self.collection_name) if item.parent_id == parent_id],
                key=lambda i: i.order
            )
            for item in children:
                collected.append((item, level))
                if item.type == 'FOLDER':
                    collected.extend(collect_items(item.id, level + 1))
            return collected
        test = collect_items(-1, 0)
        # print("Flattened hierarchy:", [v[0].id for v in test])
        # print("Expected flattened:", [v.id for v in flattened])
        return test
    
    def get_item_level_from_id(self, item_id):
        """Get the level of an item in the hierarchy"""
        item = self.get_item_by_id(item_id)
        if not item:
            return -1

        level = 0
        while item.parent_id != -1:
            item = self.get_item_by_id(item.parent_id)
            level += 1

        return level

    def normalize_orders(self):
        """Normalize orders to be sequential starting from 1 within each parent level"""
        # Group items by parent_id
        parent_groups = {}
        for item in getattr(self, self.collection_name):
            if item.parent_id not in parent_groups:
                parent_groups[item.parent_id] = []
            parent_groups[item.parent_id].append(item)

        # Sort and reassign orders within each parent group
        for parent_id, items in parent_groups.items():
            sorted_items = sorted(items, key=lambda x: x.order)
            for index, item in enumerate(sorted_items, start=1):  # Start from 1
                item.order = index

    def get_next_sibling_item(self, flattened, current_flat_index):
        """
        Get the next sibling item, skipping over children if the current item is a folder.
        Returns (item, index) or (None, -1) if not found.
        """
        current_item, current_level = flattened[current_flat_index]

        # Find where this folder's contents end
        if current_item.type == 'FOLDER':
            i = current_flat_index + 1
            while i < len(flattened):
                item, level = flattened[i]
                if level <= current_level:
                    return (item, i)
                i += 1
        else:
            # For non-folders, just get the next item
            if current_flat_index + 1 < len(flattened):
                return (flattened[current_flat_index + 1][0], current_flat_index + 1)

        return (None, -1)

    def get_movement_options(self, item_id, direction):
        """
        Analyze possible movement options for an item.
        Returns a list of possible actions and their descriptions.
        """
        item = self.get_item_by_id(item_id)
        if not item:
            return []

        flattened = self.flatten_hierarchy()
        current_flat_index = next(
            (i for i, (it, _) in enumerate(flattened) if it.id == item_id), -1)
        options = []

        if direction == 'UP':
            if current_flat_index > 0:
                above_item, _ = flattened[current_flat_index - 1]

                # Special case: If the above item is the parent folder
                if above_item.id == item.parent_id:
                    options.append(
                        ('MOVE_OUT', f"Move out of '{above_item.name}'"))
                    return options  # Only show this option in this case

                # Normal cases
                if above_item.type == 'FOLDER':
                    options.append(
                        ('MOVE_INTO', f"Move into '{above_item.name}'"))
                if above_item.parent_id != item.parent_id:
                    parent = self.get_item_by_id(above_item.parent_id)
                    parent_name = parent.name if parent else "root"
                    options.append(
                        ('MOVE_ADJACENT', f"Move into '{parent_name}'"))
                options.append(('SKIP', "Skip over"))

            # Check if at top of current parent
            siblings = sorted(
                [i for i in getattr(self, self.collection_name) if i.parent_id == item.parent_id], key=lambda x: x.order)
            if item.order == 0 and item.parent_id != -1:  # At top of current parent and not at root
                parent = self.get_item_by_id(item.parent_id)
                if parent:
                    options.append(
                        ('MOVE_OUT', f"Move out of '{parent.name}'"))

        else:  # DOWN
            # Get next sibling item (skipping folder contents if necessary)
            next_item, next_index = self.get_next_sibling_item(
                flattened, current_flat_index)

            if next_item is None:  # At bottom of its level
                if item.parent_id != -1:  # If not at root level
                    parent = self.get_item_by_id(item.parent_id)
                    if parent:
                        options.append(
                            ('MOVE_OUT_BOTTOM', f"Move out of '{parent.name}'"))
            else:
                if next_item.type == 'FOLDER':
                    options.append(
                        ('MOVE_INTO_TOP', f"Move into '{next_item.name}'"))
                if next_item.parent_id != item.parent_id:
                    parent = self.get_item_by_id(next_item.parent_id)
                    parent_name = parent.name if parent else "root"
                    options.append(
                        ('MOVE_ADJACENT', f"Move into '{parent_name}'"))
                options.append(('SKIP', "Skip over"))

        return options

    def get_movement_menu_items(self, item_id, direction):
        """
        Get menu items for movement options.
        Returns list of tuples (identifier, label, description)
        """
        options = self.get_movement_options(item_id, direction)
        menu_items = []

        # Map option identifiers to their operators
        operator_map = {
            'UP': 'nested_list.move_up',
            'DOWN': 'nested_list.move_down'
        }

        for identifier, description in options:
            menu_items.append((
                operator_map[direction],
                description,
                {'action': identifier}
            ))

        return menu_items

    def move_item_out_of_folder(self, item, parent, direction):
        """Move item out of its current folder"""
        grandparent_id = parent.parent_id

        if direction == 'UP':
            # Move item out to grandparent level at parent's position
            item.parent_id = grandparent_id
            item.order = parent.order

            # Shift parent and siblings down
            for sibling in getattr(self, self.collection_name):
                if sibling.parent_id == grandparent_id and sibling.order >= parent.order:
                    sibling.order += 1
        else:  # DOWN
            # Move to bottom of grandparent level
            max_order = max(
                (i.order for i in getattr(self, self.collection_name) if i.parent_id == grandparent_id),
                default=-1
            )
            item.parent_id = grandparent_id
            item.order = max_order + 1

        return True

    def move_item_into_folder(self, item, target_folder, position='BOTTOM'):
        """Move item into a folder at specified position (TOP or BOTTOM)"""
        item.parent_id = target_folder.id

        if position == 'TOP':
            # Shift existing items down
            for other in getattr(self, self.collection_name):
                if other.parent_id == target_folder.id:
                    other.order += 1
            item.order = 0
        else:  # BOTTOM
            item.order = self.get_next_order(target_folder.id)

        return True

    def move_item_adjacent(self, item, target_item, direction):
        """Move item as sibling of target item"""
        item.parent_id = target_item.parent_id

        if direction == 'UP':
            item.order = target_item.order + 1
        else:  # DOWN
            item.order = target_item.order
            # Shift other items
            for other in getattr(self, self.collection_name):
                if (other.parent_id == target_item.parent_id and
                    other.order >= target_item.order and
                        other.id != item.id):
                    other.order += 1

        return True

    def skip_over_item(self, item, siblings, direction):
        """Simple reorder within same parent level"""
        idx = siblings.index(item)

        if direction == 'UP' and idx > 0:
            item.order, siblings[idx -
                                 1].order = siblings[idx - 1].order, item.order
            return True
        elif direction == 'DOWN' and idx < len(siblings) - 1:
            item.order, siblings[idx +
                                 1].order = siblings[idx + 1].order, item.order
            return True

        return False

    def execute_movement(self, item_id, direction, action):
        """Execute the selected movement action."""
        item = self.get_item_by_id(item_id)
        if not item:
            return False

        flattened = self.flatten_hierarchy()
        current_flat_index = next(
            (i for i, (it, _) in enumerate(flattened) if it.id == item_id), -1)

        # Handle moving out of folder
        if action in ['MOVE_OUT', 'MOVE_OUT_BOTTOM'] and item.parent_id != -1:
            parent = self.get_item_by_id(item.parent_id)
            if parent:
                return self.move_item_out_of_folder(item, parent, direction)

        # Get relevant items based on direction
        if direction == 'UP':
            if current_flat_index > 0:
                target_item, _ = flattened[current_flat_index - 1]

                if action == 'MOVE_INTO' and target_item.type == 'FOLDER':
                    return self.move_item_into_folder(item, target_item, 'BOTTOM')
                elif action == 'MOVE_ADJACENT':
                    return self.move_item_adjacent(item, target_item, direction)
                elif action == 'SKIP':
                    siblings = sorted(
                        [i for i in getattr(self, self.collection_name) if i.parent_id == item.parent_id],
                        key=lambda x: x.order
                    )
                    return self.skip_over_item(item, siblings, direction)
        else:  # DOWN
            next_item, _ = self.get_next_sibling_item(
                flattened, current_flat_index)

            if next_item:
                if action == 'MOVE_INTO_TOP' and next_item.type == 'FOLDER':
                    return self.move_item_into_folder(item, next_item, 'TOP')
                elif action == 'MOVE_ADJACENT':
                    return self.move_item_adjacent(item, next_item, direction)
                elif action == 'SKIP':
                    siblings = sorted(
                        [i for i in getattr(self, self.collection_name) if i.parent_id == item.parent_id],
                        key=lambda x: x.order
                    )
                    return self.skip_over_item(item, siblings, direction)

        return False


class NLM_OT_MoveUp(Operator):
    bl_idname = "nested_list.move_up"
    bl_label = "Move Item Up"

    action: EnumProperty(
        items=[
            ('MOVE_INTO', "Move Into", "Move into folder"),
            ('MOVE_ADJACENT', "Move Adjacent", "Move as sibling"),
            ('MOVE_OUT', "Move Out", "Move out of folder"),
            ('SKIP', "Skip", "Skip over item"),
        ]
    )

    def invoke(self, context, event):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        options = manager.get_movement_options(item_id, 'UP')
        if not options:
            return {'CANCELLED'}

        if len(options) == 1 and options[0][0] == 'SKIP':
            self.action = 'SKIP'
            return self.execute(context)

        context.window_manager.popup_menu(
            self.draw_menu,
            title="Move Options"
        )
        return {'FINISHED'}

    def draw_menu(self, self_menu, context):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        for op_id, label, props in manager.get_movement_menu_items(item_id, 'UP'):
            op = self_menu.layout.operator(op_id, text=label)
            for key, value in props.items():
                setattr(op, key, value)

    def execute(self, context):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        if manager.execute_movement(item_id, 'UP', self.action):
            # Update active_index to follow the moved item
            flattened = manager.flatten_hierarchy()
            for i, (item, _) in enumerate(flattened):
                if item.id == item_id:
                    manager.active_index = i
                    break
            manager.normalize_orders()
            return {'FINISHED'}

        return {'CANCELLED'}


class NLM_OT_MoveDown(Operator):
    bl_idname = "nested_list.move_down"
    bl_label = "Move Item Down"

    action: EnumProperty(
        items=[
            ('MOVE_OUT_BOTTOM', "Move Out Bottom", "Move out of folder"),
            ('MOVE_INTO_TOP', "Move Into Top", "Move to top of folder"),
            ('MOVE_ADJACENT', "Move Adjacent", "Move as sibling"),
            ('SKIP', "Skip", "Skip over item"),
        ]
    )

    def invoke(self, context, event):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        options = manager.get_movement_options(item_id, 'DOWN')
        if not options:
            return {'CANCELLED'}

        if len(options) == 1 and options[0][0] == 'SKIP':
            self.action = 'SKIP'
            return self.execute(context)

        context.window_manager.popup_menu(
            self.draw_menu,
            title="Move Options"
        )
        return {'FINISHED'}

    def draw_menu(self, self_menu, context):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        for op_id, label, props in manager.get_movement_menu_items(item_id, 'DOWN'):
            op = self_menu.layout.operator(op_id, text=label)
            for key, value in props.items():
                setattr(op, key, value)

    def execute(self, context):
        manager = context.scene.nested_list_manager
        item_id = manager.get_id_from_flattened_index(manager.active_index)

        if manager.execute_movement(item_id, 'DOWN', self.action):
            # Update active_index to follow the moved item
            flattened = manager.flatten_hierarchy()
            for i, (item, _) in enumerate(flattened):
                if item.id == item_id:
                    manager.active_index = i
                    break
            manager.normalize_orders()
            return {'FINISHED'}

        return {'CANCELLED'}


class NLM_OT_NormalizeOrders(Operator):
    bl_idname = "nested_list.normalize_orders"
    bl_label = "Normalize Orders"

    def execute(self, context):
        manager = context.scene.nested_list_manager
        manager.normalize_orders()
        return {'FINISHED'}


classes = (
    NLM_OT_MoveUp,
    NLM_OT_MoveDown,
    NLM_OT_NormalizeOrders,
)

register, unregister = register_classes_factory(classes)