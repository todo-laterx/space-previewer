%global _python_bytecompile_extra 0
%undefine __brp_python_bytecompile

Name:           space-previewer
Version:        %{app_version}
Release:        1
Summary:        Quick Look file previewer for Nautilus and Dolphin
License:        GPL-3.0-only
URL:            https://github.com/todo-laterx/space-previewer
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch
BuildRequires:  gettext
Requires:       python3
Requires:       python3-gobject
Requires:       python3-cairo
Requires:       python3-pygments
Requires:       python3-markdown-it
Requires:       gtk4
Requires:       libadwaita
Requires:       gdk-pixbuf2
Requires:       pango
Requires:       poppler-glib
Recommends:     webkitgtk6.0
Recommends:     nautilus
Recommends:     dolphin
Recommends:     nemo
# Both packages own org.gnome.NautilusPreviewer.service; RPM has no dpkg-divert.
Conflicts:      sushi

%description
GTK4 and Libadwaita file previews for images, text, Markdown, PDFs, Office
documents, archives and media. Includes a Dolphin service menu for local
files and folders, and the Nautilus D-Bus preview service. This package is an
alternative to Sushi and cannot be installed alongside it.

%prep
%setup -q

%build
for po_file in po/*.po; do
    lang=$(basename "$po_file" .po)
    mkdir -p "locale/$lang/LC_MESSAGES"
    msgfmt --check -o "locale/$lang/LC_MESSAGES/space-previewer.mo" "$po_file"
done

%install
mkdir -p %{buildroot}%{_datadir}/space-previewer
cp -a src/. %{buildroot}%{_datadir}/space-previewer/
cp -a locale %{buildroot}%{_datadir}/space-previewer/
install -Dm644 data/space-previewer.desktop \
    %{buildroot}%{_datadir}/kio/servicemenus/space-previewer.desktop
install -Dm644 data/space-previewer.nemo_action \
    %{buildroot}%{_datadir}/nemo/actions/space-previewer.nemo_action
install -Dm644 assets/logo-512.png \
    %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/space-previewer.png
mkdir -p %{buildroot}%{_bindir}
cat > %{buildroot}%{_bindir}/space-previewer <<'EOF'
#!/bin/sh
exec /usr/bin/python3 /usr/share/space-previewer/main.py "$@"
EOF
chmod 0755 %{buildroot}%{_bindir}/space-previewer
mkdir -p %{buildroot}%{_datadir}/dbus-1/services
cat > %{buildroot}%{_datadir}/dbus-1/services/org.gnome.NautilusPreviewer.service <<'EOF'
[D-BUS Service]
Name=org.gnome.NautilusPreviewer
Exec=/usr/bin/python3 /usr/share/space-previewer/main.py
EOF
find "%{buildroot}%{_datadir}/space-previewer" -type d -name __pycache__ -prune -exec rm -rf {} +
find "%{buildroot}%{_datadir}/space-previewer" -type f -name '*.pyc' -delete

%files
%license LICENSE
%doc README.md TRADEMARK.md docs/DOLPHIN.md docs/INTEGRATIONS.md
%{_bindir}/space-previewer
%{_datadir}/space-previewer/
%{_datadir}/kio/servicemenus/space-previewer.desktop
%{_datadir}/nemo/actions/space-previewer.nemo_action
%{_datadir}/dbus-1/services/org.gnome.NautilusPreviewer.service
%{_datadir}/icons/hicolor/512x512/apps/space-previewer.png
