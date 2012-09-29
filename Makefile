all: pdf-edit

clean:
	rm -f pdf-edit

PREFIX=/usr/local
install: pdf-edit
	install -m 755 --owner root --group root pdf-edit $(PREFIX)/bin/

.PHONY: all clean install

pdf-edit: pdfedit/*.py
	zip --quiet --junk-paths pdf-edit pdfedit/*.py
	echo '#!/usr/bin/env python' > pdf-edit
	cat pdf-edit.zip >> pdf-edit
	rm pdf-edit.zip
	chmod a+x pdf-edit
