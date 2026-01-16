
content = open('post/templates/trsection_detail.html').read()

# Add Edit Annotation buttons and editor containers
import re

# Find <h5 class="mb-2">{{ child.section }}. {{ child.text|safe }}</h5> patterns and add button after
# This is complex, so let me just do simple search/replace

# Replace specific section with button
old1 = '''<h5 class="mb-2">{{ child.section }}. {{ child.text|safe }}</h5>'''
new1 = '''<div class="d-flex justify-content-between align-items-start">
                                    <h5 class="mb-2">{{ child.section }}. {{ child.text|safe }}</h5>
                                    {% if user.is_authenticated %}
                                        <button class="btn btn-sm btn-outline-primary ms-2 edit-annotation-btn" data-section="{{ child.section }}" data-rule-type="TR">Edit Annotation</button>
                                    {% endif %}
                                </div>
                                <div id="editor-container-{{ child.section }}" class="editor-container" style="display: none;">
                                    <div id="editor-{{ child.section }}" class="mb-2"></div>
                                    <button class="btn btn-sm btn-success save-annotation-btn" data-section="{{ child.section }}">Save</button>
                                    <button class="btn btn-sm btn-secondary cancel-annotation-btn" data-section="{{ child.section }}">Cancel</button>
                                </div>'''

content = content.replace(old1, new1)

with open('post/templates/trsection_detail.html', 'w') as f:
    f.write(content)
print('Done')
