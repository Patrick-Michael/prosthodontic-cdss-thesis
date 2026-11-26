<!DOCTYPE html>
<html lang=${language}>
<head><meta charset='UTF-8'>
    <title>${guide.id}</title>
    <style>
        body {font-family: Calibri;}
        td { vertical-align: top; }
        h1 {font-size: 26px; margin:0px;}
        h2 {background-color: #4f81bd; color: white; padding: 5px;  font-size: 110%; margin-bottom:0px; margin-top:10px; font-weight: bold;}
        h3 {background-color: #9ec2ef;  padding-bottom: 8px; padding-left: 5px; margin-bottom:0px; margin-top:0px;}
        .bg-block {background-color: #dbe5f1;  padding-bottom: 8px; margin-bottom: 5px;;}
        .details-label {font-weight: bold; margin-right: 5px;}
    </style>
</head>
<body>
<h1>${guide_terms["gt0001"].text?if_exists}</h1>

<h2>${texts.GuideDetails?upper_case}</h2>
<table>
    <tr valign='top'><td class="details-label">${texts.Description}:</td><td align='left'>${guide_terms["gt0001"].description?if_exists?replace("\n", "<br>")}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Purpose}:</td><td align='left'>${guide_purpose?if_exists?replace("\n", "<br>")}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Use}:</td><td align='left'>${guide_use?if_exists?replace("\n", "<br>")}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Misuse}:</td><td align='left'>${guide_misuse?if_exists?replace("\n", "<br>")}</td></tr>
    <tr valign='top'><td class="details-label">${texts.References}:</td><td align='left'>${guide_references?if_exists?replace("\n", "<br>")}</td></tr>
</table>

<h2>${texts.AuthorDetails?upper_case}</h2>
<table>
    <tr valign='top'><td class="details-label">${texts.Name}: </td><td align='left'>${guide.gdlDescription.gdlAuthorDetails.name?if_exists}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Email}: </td><td align='left'>${guide.gdlDescription.gdlAuthorDetails.email?if_exists}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Organisation}: </td><td align='left'>${guide.gdlDescription.gdlAuthorDetails.organization?if_exists}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Date}: </td><td align='left'>${guide.gdlDescription.gdlAuthorDetails.authoredDate?if_exists}</td></tr>
    <tr valign='top'><td class="details-label">${texts.AuthorshipLifecycle}: </td><td align='left'>${guide.gdlDescription.lifeCycleState?if_exists}</td></tr>
    <tr valign='top'><td class="details-label">${texts.Copyright}: </td><td align='left'>${guide_copyright?if_exists}</td></tr>
</table>

<#if guide_keywords?has_content>
    <h2>${texts.Keywords?upper_case}</h2>
    <#list guide_keywords as keyword><i>
        ${keyword}<#if keyword_has_next>, </#if>
    </i></#list>
    <br>
</#if>

<#if guide_otherContributors?has_content>
    <h2>${texts.Contributors?upper_case}</h2>
    <#list guide_otherContributors as otherContributor><i>
        ${otherContributor}<#if otherContributor_has_next>, </#if>
    </i></#list>
    <br>
</#if>

<h2>${texts.Definitions?upper_case}</h2>
<#if guide_definitions_input?has_content>
    <h3>INPUT</h3>
    <#list guide_definitions_input as definition>
        <div class="bg-block">
            ${definition}
        </div>
    </#list>
</#if>
<#if guide_definitions_output?has_content>
<h3>OUTPUT</h3>
    <#list guide_definitions_output as definitionRuleLine>
    <div class="bg-block">
    ${definitionRuleLine}
    </div>
    </#list>
</#if>
<#if guide_definitions_any?has_content>
<h3>ANY</h3>
    <#list guide_definitions_any as definitionRuleLine>
    <div class="bg-block">
    ${definitionRuleLine}
    </div>
    </#list>
</#if>

<#if guide_term_bindings?? && guide_term_bindings?has_content>
    <h2>${texts.Bindings?upper_case}</h2>
    <#list guide_term_bindings?keys as termBindingKey>
        <h3>${termBindingKey}</h3>
        <div class="bg-block">
            <table>
                <#list guide_term_bindings[termBindingKey] as binding>
                 <tr><td class="details-label">${binding.term.text}:</td>
                 <td>
                 <#list binding.codes as code>
                    ${code.code}<#if code_has_next>, </#if>
                 </#list>
                 </td></tr>
                </#list>
            </table>
        </div>
        <br>
    </#list>
    <br>
</#if>
</body>
</html>
