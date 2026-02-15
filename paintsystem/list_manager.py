import bpy

class ListManager:
    """
    A generic class to manage reordering, adding, and removing items 
    in a Blender collection property.
    """

    def __init__(self, data_ptr, propname, 
                 active_dataptr, active_propname):
        """
        Initialize the ListOrganizer.

        :param data_holding_collection: The data block instance holding the collection property (e.g., scene, object, material).
        :param collection_prop_name: The string name of the collection property.
        :param data_holding_active_index: The data block instance holding the active index property.
        :param active_index_prop_name: The string name of the integer property for the active index.
        """
        self.data_ptr = data_ptr
        self.propname = propname
        self.active_dataptr = active_dataptr
        self.active_propname = active_propname

    @property
    def collection(self):
        """Dynamically gets the collection from the data block."""
        return getattr(self.data_ptr, self.propname)

    @property
    def active_index(self):
        """Dynamically gets the active index from its data block."""
        return getattr(self.active_dataptr, self.active_propname)

    @active_index.setter
    def active_index(self, value):
        """Dynamically sets the active index on its data block."""
        setattr(self.active_dataptr, self.active_propname, value)

    def move_active_up(self):
        """Move the active item up in the list."""
        if 'UP' not in self.possible_moves():
            return

        new_index = self.active_index - 1
        self.collection.move(self.active_index, new_index)
        self.active_index = new_index

    def move_active_down(self):
        """Move the active item down in the list."""
        if 'DOWN' not in self.possible_moves():
            return

        new_index = self.active_index + 1
        self.collection.move(self.active_index, new_index)
        self.active_index = new_index
        
    def add_item(self):
        """Add a new item to the list."""
        item = self.collection.add()
        item.name = f"Item {len(self.collection)}"
        self.active_index = len(self.collection) - 1
        return item

    def remove_active_item(self):
        """Remove the active item from the list."""
        if not self.collection or self.active_index < 0:
            return

        self.collection.remove(self.active_index)
        # Adjust active index if it's out of bounds
        if self.active_index >= len(self.collection):
            self.active_index = len(self.collection) - 1

    def possible_moves(self):
        """Determine possible moves for the active item ('UP', 'DOWN')."""
        moves = []
        if not self.collection or self.active_index < 0:
            return moves

        if self.active_index > 0:
            moves.append('UP')
        if self.active_index < len(self.collection) - 1:
            moves.append('DOWN')
        return moves
