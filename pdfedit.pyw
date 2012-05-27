#!/usr/bin/env python

import os
import sys
import time
from PyQt4.QtCore import *
from PyQt4.QtGui import *

#Thanks to Mathieu Fenniak and Ashish Kulkarni <kulkarni.ashish@gmail.com> for:
import pyPdf

__author__ = "Viranch Mehta"
__author_email__ = "viranch.mehta@gmail.com"
__version__ = '0.9'

class Item (QObject):

    def __init__ (self, filename, parent, index):
        super (Item, self).__init__(parent)
        self.filename = filename
        self.parent = parent
        self.index = index
        
        self.name = self.filename.split('/')[-1]
        self.first = 0
        f=open(self.filename, 'rb')
        pdf = pyPdf.PdfFileReader(f)
        if pdf.isEncrypted: pdf.decrypt('')
        self.length = pdf.numPages
        f.close()
        self.last = self.length-1
        self.pages = self.length
        self.createSpins()

    def createSpins ( self ):
        self.firstSpin = QSpinBox()
        self.firstSpin.setRange ( 1, self.length )
        self.firstSpin.setValue ( self.first+1 )
        self.lastSpin = QSpinBox()
        self.lastSpin.setRange ( 1, self.length )
        self.lastSpin.setValue ( self.last+1 )
        self.connect (self.firstSpin, SIGNAL('valueChanged(int)'), self.setFirstTime)
        self.connect (self.lastSpin, SIGNAL('valueChanged(int)'), self.setLastTime)

    def setFirstTime (self, value):
        self.first = value-1
        self.lastSpin.setMinimum ( value )
        self.parent.table.topLevelItem(self.index).setText ( 3, str(self.last-self.first+1) )

    def setLastTime (self, value):
        self.last = value-1
        self.firstSpin.setMaximum ( value )
        self.parent.table.topLevelItem(self.index).setText ( 3, str(self.last-self.first+1) )

    def upPages (self):
        self.pages = self.last-self.first+1
        return self.pages
    
    def getPages (self):
        pages = []
        f=open(self.filename, 'rb')
        pdf = pyPdf.PdfFileReader(f)
        if pdf.isEncrypted: pdf.decrypt('')
        for pgno in range (self.first, self.last+1):
            pages.append ( pdf.getPage (pgno) )
        f.close()
        return pages

class MainWindow(QMainWindow):

    def __init__ ( self, parent=None ):
        super (MainWindow, self).__init__(parent)

        self.items = []
        icon = lambda name: os.path.dirname(__file__)+'/icons/'+name
        centralWidget = QWidget(self)

        self.toolbar = self.addToolBar ('Toolbar')
        self.status = self.statusBar()
        self.status.showMessage ('Ready')

        self.table = QTreeWidget(centralWidget)
        headerItem = self.table.headerItem()
        headerItem.setIcon (0, QIcon(icon('application-pdf.png')))
        headerItem.setText (0, 'Filename')
        headerItem.setIcon (1, QIcon(icon('flag-green.png')))
        headerItem.setText (1, 'From Page')
        headerItem.setIcon (2, QIcon(icon('flag-red.png')))
        headerItem.setText (2, 'To Page')
        headerItem.setIcon (3, QIcon(icon('edit-copy.png')))
        headerItem.setText (3, 'Pages')
        self.table.setRootIsDecorated (False)
        self.setCentralWidget (centralWidget)
        
        addAction = self.createAction ('Add', self.add, 'Ctrl+O', 'Add...', icon('document-new.png'))
        rmAction = self.createAction ('Remove', self.remove, 'Del', 'Remove', icon('document-close.png'))
        clearAction = self.createAction ('Clear', self.clear, 'Shift+Del', 'Clear', icon('edit-clear-list.png'))
        upAction = self.createAction ('Up', self.up, 'Ctrl+Up', 'Shift Up', icon('go-up.png'))
        downAction = self.createAction ('Down', self.down, 'Ctrl+Down', 'Shift Down', icon('go-down.png'))
        saveAction = self.createAction ('Save', self.save, QKeySequence.Save, 'Save', icon('document-save-as.png'))
        aboutAction = self.createAction ('About', self.about, None, 'About', icon('help-about.png'))
        quitAction = self.createAction ('Quit', self.close, 'Ctrl+Q', 'Quit', icon('application-exit.png'))
        
        self.toolbar.addAction ( addAction )
        self.toolbar.addAction ( rmAction )
        self.toolbar.addAction ( clearAction )
        self.toolbar.addSeparator()
        self.toolbar.addAction ( saveAction )
        self.toolbar.addSeparator()
        self.toolbar.addAction ( upAction )
        self.toolbar.addAction ( downAction )
        self.toolbar.addSeparator()
        self.toolbar.addAction ( aboutAction )
        self.toolbar.addAction ( quitAction )

        grid = QGridLayout()
        grid.addWidget (self.table, 0, 0)
        centralWidget.setLayout (grid)

        self.resize (415, 377)
        self.setWindowTitle ('PDF Edit')
        self.setWindowIcon ( QIcon(icon('acroread.png')) )
        
    def add (self):
        filenames = QFileDialog (self).getOpenFileNames()
        for filename in filenames:
            try:
                filename = str(filename)
                if filename.split('.')[-1].lower() != 'pdf':
                    continue
                new = Item (filename, self, len(self.items))
                self.items.append (new)
                new_item = QTreeWidgetItem ([new.name, '', '', str(new.length)])
                self.table.addTopLevelItem ( new_item )
                self.table.setItemWidget ( new_item, 1, new.firstSpin )
                self.table.setItemWidget ( new_item, 2, new.lastSpin )
            except Exception as err:
                QMessageBox.critical (self, 'Error', 'The following error occured:\n'+str(err))
        self.table.setCurrentItem ( self.table.topLevelItem (self.table.topLevelItemCount()-1) )
        self.status.showMessage ('File(s) added.', 5000)

    def remove (self):
        if len(self.items) == 0:
            self.status.showMessage ('Nothing to remove!', 5000)
            return None
        current = self.table.indexOfTopLevelItem ( self.table.currentItem() )
        popped = self.table.takeTopLevelItem (current)
        rm = self.items.pop (current)
        self.status.showMessage (rm.name+' removed', 5000)
        self.updateSpins()
        return popped, rm

    def clear (self):
        if len(self.items)==0:
            self.status.showMessage ('List already clear!', 5000)
            return None
        self.table.clear()
        self.items = []
        self.status.showMessage ('List cleared', 5000)

    def move (self, to):
        if len(self.items)<2:
            return None
        current = self.table.indexOfTopLevelItem ( self.table.currentItem() )
        if current == (len(self.items)-1)*(to>0):
            return None
        toPos = current+to
        tmp1 = self.table.takeTopLevelItem (current)
        tmp2 = self.items.pop (current)
        
        self.table.insertTopLevelItem ( toPos, tmp1 )
        self.items.insert ( toPos, tmp2 )
        self.updateSpins()
        self.table.setCurrentItem ( self.table.topLevelItem(toPos) )

    def up (self): self.move (-1)

    def down (self): self.move (1)
    
    def updateSpins ( self ):
        for i in range ( len(self.items) ):
            self.items[i].createSpins()
            self.table.setItemWidget ( self.table.topLevelItem(i), 1, self.items[i].firstSpin )
            self.table.setItemWidget ( self.table.topLevelItem(i), 2, self.items[i].lastSpin )
            self.items[i].index = i

    def save (self):
        if len(self.items) == 0:
            self.status.showMessage ( 'Nothing to save!', 5000 )
            return None
        save_file = str ( QFileDialog (self).getSaveFileName() )
        self.status.showMessage ( 'Saving...' )
        if os.access (save_file, os.F_OK):
            os.remove (save_file)
        output = pyPdf.PdfFileWriter()
        fs = []
        for item in self.items:
            fs.append ( open(item.filename, 'rb') )
            pdf = pyPdf.PdfFileReader(fs[-1])
            if pdf.isEncrypted: pdf.decrypt('')
            for pgno in range (item.first, item.last+1):
                output.addPage ( pdf.getPage (pgno) )
        f=open (save_file, 'wb')
        try:
            output.write ( f )
            f.close()
        except Exception as err:
            f.close()
            os.remove (save_file)
            QMessageBox.critical (self, 'Error', str(err))
        for f in fs: f.close()
        del fs
        self.status.showMessage ( 'Saved to '+save_file.split(os.sep)[-1], 5000 )

    def about (self):
        return

    def createAction (self, text, slot=None, shortcut=None, tip=None, icon=None, checkable=None, signal='triggered()'):
        action = QAction (text, self)
        if icon is not None:
            action.setIcon (QIcon (icon))
        if shortcut is not None:
            action.setShortcut (shortcut)
        if tip is not None:
            action.setToolTip (tip)
            action.setStatusTip (tip)
        if slot is not None:
            self.connect (action, SIGNAL(signal), slot)
        if checkable:
            action.setCheckable (True)
        return action

if __name__=='__main__':
    app = QApplication (sys.argv)
    window = MainWindow()
    window.show()
    app.exec_()
