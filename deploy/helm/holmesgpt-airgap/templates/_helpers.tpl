{{/*
Return the service account name to use
*/}}
{{- define "holmesgpt.serviceAccountName" -}}
{{- if .Values.customServiceAccountName -}}
{{ .Values.customServiceAccountName }}
{{- else if .Values.createServiceAccount -}}
{{ .Release.Name }}-holmes-service-account
{{- else -}}
default
{{- end -}}
{{- end -}}

{{/*
Generate full image reference
*/}}
{{- define "holmesgpt.image" -}}
{{ .Values.registry }}/{{ .Values.image }}
{{- end -}}
