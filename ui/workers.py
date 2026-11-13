"""Qt adapter for core.operations: marshals the worker-thread completion callback onto the
GUI thread via a queued signal. (Written for PySide6; NOT executed in the development
sandbox where PySide6 is unavailable - see the 0.3 test report.)"""
from PySide6.QtCore import QObject, Signal


class OperationNotifier(QObject):
    finished = Signal(object)          # emits the finished core.operations.Operation

    def callback(self, op):            # called from the worker thread
        self.finished.emit(op)         # delivered on the GUI thread (queued connection)
