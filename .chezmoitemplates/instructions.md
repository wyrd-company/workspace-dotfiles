{{ include ".includes/CORE-INSTRUCTIONS.md" -}}
{{- /* Fork notes: docs/fork-overlay.md. glob and joinPath need an absolute path, since glob resolves against the working directory. */ -}}
{{- $notes := glob (joinPath .chezmoi.sourceDir ".includes" "fork" "*.md") | sortAlpha -}}
{{- if $notes }}
<fork-instructions>
{{- range $notes }}
{{ include . | trim }}
{{- end }}
</fork-instructions>
{{ end -}}
