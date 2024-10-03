<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:xs="http://www.w3.org/2001/XMLSchema"
    xmlns:alto="http://www.loc.gov/standards/alto/ns-v4#"
    exclude-result-prefixes="xs alto"
    version="1.0">
    
    <!-- Output formatting -->
    <xsl:output indent="yes" method="xml" encoding="UTF-8"/>
    
    <!-- Define a key for faster lookup -->
    <xsl:key name="label" match="alto:OtherTag" use="@ID" />
    
    <!-- Template to match the root 'alto' element -->
    <xsl:template match="/alto:alto">
        <doc>
            <!-- Apply templates to all TextBlock elements -->
            <xsl:apply-templates select="//alto:TextBlock"/>
        </doc>
    </xsl:template>
    
    <!-- Template to match TextBlock -->
    <xsl:template match="alto:TextBlock">
        <region>
            <!-- Using the key to lookup 'OtherTag' by ID -->
            <xsl:attribute name="type">
                <xsl:value-of select="key('label', @TAGREFS)/@LABEL"/>
            </xsl:attribute>
            <!-- Apply templates to nested TextLine elements -->
            <xsl:apply-templates select=".//alto:TextLine"/>
        </region>
    </xsl:template>
    
    <!-- Template to match TextLine -->
    <xsl:template match="alto:TextLine">
        <line>
            <!-- Again, use the key to lookup 'OtherTag' by ID -->
            <xsl:attribute name="type">
                <xsl:value-of select="key('label', @TAGREFS)/@LABEL"/>
            </xsl:attribute>
            <!-- Apply templates to String and SP elements -->
            <xsl:apply-templates select="alto:String|alto:SP" />
        </line>
    </xsl:template>
    
    <!-- Template to match String element -->
    <xsl:template match="alto:String">
        <xsl:value-of select="@CONTENT"/>
    </xsl:template>
    
    <!-- Template to match SP (space) element -->
    <xsl:template match="alto:SP">
        <xsl:text> </xsl:text>
    </xsl:template>
    
</xsl:stylesheet>

