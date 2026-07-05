import html


def render_page(title: str, body: str) -> str:
    """Wrap body HTML in the shared Sentinel page shell (header, icon, dark theme)."""
    return (
        '<!DOCTYPE html>\n'
        '<html lang="en" class="h-full bg-gray-950">\n'
        '<head>\n'
        '  <meta charset="UTF-8">\n'
        '  <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f'  <title>{html.escape(title)}</title>\n'
        '  <link rel="icon" href="/static/icon.png">\n'
        '  <script src="https://cdn.tailwindcss.com"></script>\n'
        '  <style>\n'
        '    .badge-online  { @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-500/20 text-emerald-400 ring-1 ring-emerald-500/30; }\n'
        '    .badge-offline { @apply inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-gray-700 text-gray-400 ring-1 ring-gray-600; }\n'
        '  </style>\n'
        '</head>\n'
        '<body class="h-full text-gray-100 font-sans">\n'
        '  <header class="border-b border-gray-800 px-6 py-4 flex items-center justify-between">\n'
        '    <a href="/" class="flex items-center gap-3">\n'
        '      <img src="/static/icon.png" class="w-8 h-8 rounded-lg object-cover">\n'
        '      <span class="text-lg font-semibold tracking-tight">Sentinel</span>\n'
        '    </a>\n'
        '  </header>\n'
        '  <main class="max-w-7xl mx-auto px-6 py-8 space-y-8">\n'
        f'{body}\n'
        '  </main>\n'
        '</body>\n'
        '</html>\n'
    )
